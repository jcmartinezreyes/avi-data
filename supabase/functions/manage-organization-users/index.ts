import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { ...corsHeaders, "Content-Type": "application/json" },
});

const allowedRoles = new Set(["admin", "operator", "analyst"]);

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return response({ error: "Método no permitido." }, 405);

  const authorization = req.headers.get("Authorization");
  const token = authorization?.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!token) return response({ error: "Inicia sesión para continuar." }, 401);

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const publishableKey = Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ?? Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? Deno.env.get("SUPABASE_SECRET_KEY") ?? "";
  if (!url || !publishableKey || !serviceKey) return response({ error: "Falta configuración segura del servidor." }, 500);

  const authClient = createClient(url, publishableKey, { auth: { persistSession: false } });
  const { data: authData, error: authError } = await authClient.auth.getUser(token);
  if (authError || !authData.user) return response({ error: "Sesión inválida o vencida." }, 401);

  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
  try {
    const input = await req.json();
    const organizationId = String(input.organization_id ?? "");
    const action = String(input.action ?? "");
    if (!organizationId || !["list", "invite", "update", "remove"].includes(action)) {
      return response({ error: "Solicitud incompleta." }, 400);
    }

    const { data: callerMembership, error: membershipError } = await admin
      .from("organization_memberships").select("role")
      .eq("organization_id", organizationId).eq("user_id", authData.user.id).maybeSingle();
    if (membershipError) throw membershipError;
    if (!callerMembership || !["owner", "admin"].includes(callerMembership.role)) {
      return response({ error: "Solo un propietario o administrador puede gestionar usuarios." }, 403);
    }

    if (action === "list") {
      const [{ data: memberships, error: membersError }, { data: profiles, error: profilesError }, { data: org, error: orgError }] = await Promise.all([
        admin.from("organization_memberships").select("user_id, role, created_at").eq("organization_id", organizationId).order("created_at"),
        admin.from("user_profiles").select("user_id, full_name, username, job_title").order("full_name"),
        admin.from("organizations").select("name").eq("id", organizationId).single(),
      ]);
      if (membersError) throw membersError;
      if (profilesError) throw profilesError;
      if (orgError) throw orgError;

      const authUsers: Array<{ id: string; email?: string }> = [];
      for (let page = 1; page <= 100; page += 1) {
        const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
        if (error) throw error;
        authUsers.push(...data.users.map((u) => ({ id: u.id, email: u.email ?? undefined })));
        if (data.users.length < 1000) break;
      }
      const emailById = new Map(authUsers.map((u) => [u.id, u.email ?? ""]));
      const profileById = new Map((profiles ?? []).map((p) => [p.user_id, p]));
      return response({
        organization: org.name,
        members: (memberships ?? []).map((m) => ({
          ...profileById.get(m.user_id),
          user_id: m.user_id,
          email: emailById.get(m.user_id) ?? "",
          role: m.role,
          created_at: m.created_at,
        })),
      });
    }

    const targetId = String(input.user_id ?? "");
    if (action === "invite") {
      const email = String(input.email ?? "").trim().toLowerCase();
      const fullName = String(input.full_name ?? "").trim();
      const username = String(input.username ?? "").trim();
      const jobTitle = String(input.job_title ?? "").trim();
      const role = String(input.role ?? "operator");
      if (!email.includes("@") || !fullName || !username || !jobTitle || !allowedRoles.has(role)) {
        return response({ error: "Completa nombre, usuario, cargo, correo y un rol válido." }, 400);
      }
      let userId = "";
      for (let page = 1; page <= 100 && !userId; page += 1) {
        const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
        if (error) throw error;
        userId = data.users.find((u) => u.email?.toLowerCase() === email)?.id ?? "";
        if (data.users.length < 1000) break;
      }
      if (!userId) {
        const { data, error } = await admin.auth.admin.inviteUserByEmail(email, {
          data: { full_name: fullName, username, job_title: jobTitle },
        });
        if (error) throw error;
        if (!data.user) throw new Error("No se pudo crear la invitación.");
        userId = data.user.id;
      }
      const { error: profileError } = await admin.from("user_profiles").upsert({
        user_id: userId, full_name: fullName, username, job_title: jobTitle, updated_at: new Date().toISOString(),
      });
      if (profileError) throw profileError;
      const { error: addError } = await admin.from("organization_memberships").upsert({
        organization_id: organizationId, user_id: userId, role,
      });
      if (addError) throw addError;
      return response({ success: true, invited_email: email, role });
    }

    if (!targetId || targetId === authData.user.id) return response({ error: "Selecciona otro miembro de la organización." }, 400);
    const { data: target, error: targetError } = await admin.from("organization_memberships")
      .select("role").eq("organization_id", organizationId).eq("user_id", targetId).maybeSingle();
    if (targetError) throw targetError;
    if (!target) return response({ error: "El usuario no pertenece a esta organización." }, 404);
    if (target.role === "owner") return response({ error: "La membresía del propietario está protegida." }, 403);

    if (action === "update") {
      const role = String(input.role ?? "");
      const fullName = String(input.full_name ?? "").trim();
      const username = String(input.username ?? "").trim();
      const jobTitle = String(input.job_title ?? "").trim();
      if (!allowedRoles.has(role) || !fullName || !username || !jobTitle) return response({ error: "Completa los datos y selecciona un rol válido." }, 400);
      const { error: roleError } = await admin.from("organization_memberships").update({ role })
        .eq("organization_id", organizationId).eq("user_id", targetId);
      if (roleError) throw roleError;
      const { error: profileError } = await admin.from("user_profiles").upsert({
        user_id: targetId, full_name: fullName, username, job_title: jobTitle, updated_at: new Date().toISOString(),
      });
      if (profileError) throw profileError;
      return response({ success: true });
    }

    const { error: removeError } = await admin.from("organization_memberships").delete()
      .eq("organization_id", organizationId).eq("user_id", targetId);
    if (removeError) throw removeError;
    return response({ success: true });
  } catch (error) {
    console.error("manage-organization-users", error);
    const message = error instanceof Error ? error.message : "No se pudo completar la operación.";
    return response({ error: message }, 400);
  }
});
