const allowedOrigin = "https://monitor.hamelberg-ai.com";
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

Deno.serve(async (request) => {
  const origin = request.headers.get("origin");
  if (origin !== allowedOrigin) return new Response("Forbidden", { status: 403 });

  const headers = {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Cache-Control": "no-store",
    "Vary": "Origin"
  };
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers });

  let token;
  try {
    const body = await request.text();
    if (body.length > 128) throw new Error("Request too large");
    token = JSON.parse(body).token;
  } catch (_) {
    return new Response("Invalid request", { status: 400, headers });
  }
  if (typeof token !== "string" || !uuidPattern.test(token)) {
    return new Response("Invalid visit token", { status: 400, headers });
  }

  const apiUrl = Deno.env.get("SUPABASE_URL");
  const secretKeys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
  const apiKey = secretKeys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!apiUrl || !apiKey) return new Response("Counter unavailable", { status: 503, headers });

  const apiHeaders = {
    apikey: apiKey,
    "Content-Type": "application/json",
    ...(!apiKey.startsWith("sb_secret_") ? { Authorization: `Bearer ${apiKey}` } : {})
  };

  try {
    const result = await fetch(`${apiUrl}/rest/v1/rpc/monitor_register_visit`, {
      method: "POST",
      headers: apiHeaders,
      body: JSON.stringify({ p_token: token })
    });
    if (!result.ok) throw new Error(`Counter database returned ${result.status}`);
    const number = await result.json();
    if (!Number.isSafeInteger(number) || number < 1) throw new Error("Invalid counter response");
    return Response.json({ number }, { headers });
  } catch (error) {
    console.error(error);
    return new Response("Counter unavailable", { status: 502, headers });
  }
});
