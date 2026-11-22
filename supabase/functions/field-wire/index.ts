const origin = "https://monitor.hamelberg-ai.com";
const headers = {"Access-Control-Allow-Origin":origin,"Access-Control-Allow-Headers":"content-type",
  "Access-Control-Allow-Methods":"POST, OPTIONS","Cache-Control":"no-store","Vary":"Origin"};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
let known = new Set<string>(), expires = 0;
async function activeItem(key: string) {
  if (Date.now() >= expires) {
    const res = await fetch(origin + "/field-wire/items.json");
    if (!res.ok) throw Error("Feed unavailable");
    known = new Set(await res.json());
    expires = Date.now() + 60000;
  }
  return known.has(key);
}
Deno.serve(async req => {
  const reply = (body:unknown,status=200) => Response.json(body,{headers,status});
  if(req.headers.get("origin") !== origin) return reply({},403);
  if(req.method === "OPTIONS") return new Response(null,{status:204,headers});
  if(req.method !== "POST") return reply({},405);
  try {
    const raw = await req.text();
    if(raw.length>3000) return reply({},413);
    const {item_key,reader,action,value,request_id} = JSON.parse(raw);
    if(typeof item_key!=="string" || !uuid.test(reader) || !["read","react","view","comment"].includes(action)) return reply({},400);
    if(action==="react" && !["","like","dislike","love","thinking"].includes(value)) return reply({},400);
    if(action==="comment" && (!uuid.test(request_id) || typeof value!=="string" || !value.trim() || value.length>500)) return reply({},400);
    if(!await activeItem(item_key)) return reply({},404);
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    const key = keys.default || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    const rpc = await fetch(Deno.env.get("SUPABASE_URL")+"/rest/v1/rpc/field_wire_action",{
      method:"POST",headers:{apikey:key,"Content-Type":"application/json",...(!key.startsWith("sb_secret_")?{Authorization:"Bearer "+key}:{})},
      body:JSON.stringify({item_key,reader,action,value,request_id})
    });
    const result = await rpc.json();
    if(!rpc.ok) return reply({},result.message==="Please wait before posting again"?429:503);
    return reply(result);
  } catch { return reply({},503); }
});
