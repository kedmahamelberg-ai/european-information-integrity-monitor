# Monitor traffic reports

Use the private [Monitor SQL editor](https://supabase.com/dashboard/project/jnzibjjejmfochertwco/sql/new) for cookieless page views. This report uses the last 28 complete days in Europe/Amsterdam.

```sql
select day, sum(total) as page_views,
       coalesce(sum(total) filter (where source = 'google'), 0) as google,
       coalesce(sum(total) filter (where source = 'chatgpt'), 0) as chatgpt,
       coalesce(sum(total) filter (where source = 'claude'), 0) as claude,
       coalesce(sum(total) filter (where source = 'internal'), 0) as internal,
       coalesce(sum(total) filter (where source = 'other_referral'), 0) as other_referral,
       coalesce(sum(total) filter (where source = 'direct_or_unknown'), 0) as direct_or_unknown
from monitor_traffic_private.daily_page_views
where day >= (now() at time zone 'Europe/Amsterdam')::date - 28
  and day < (now() at time zone 'Europe/Amsterdam')::date
group by day
order by day desc;
```

The counter records each visible document once. Reloads can add views. It groups arrival sources without storing identifiers, referrer paths or URL queries. An app that removes referral information can appear under direct or unknown. The dashboard's earlier browser-token session count remains available as separate historical data in `monitor_private.visit_sessions`. Individual Field Wire participation counters remain scoped to dispatches.

Use [Search Console filtered to the Monitor](https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Ahamelberg-ai.com&page=*https%3A%2F%2Fmonitor.hamelberg-ai.com%2F) for Google search impressions and clicks. GA4 continues to use denied analytics storage.

Deploy the migration before the corresponding site update. For a controlled production check, open `/about.html?utm_source=google`, `/about.html?utm_source=chatgpt.com` and `/about.html?utm_source=claude.ai` as visible pages. Confirm the RPC returns HTTP 204 and the expected daily source rows increase. These controlled views contribute to the day's totals.

Public landing pages, dated editions and findings load GA4 and register a visit using the same 30-minute session token. The homepage displays the visit's assigned number. Earlier session totals omit readers who only visited other pages. A finding shows its 30-day page loads from four views onward. Field Wire displays distinct browsers and, from 27 November 2026, 30-day dispatch views. Seeing either copy of a dispatch headline at least halfway on screen in a visible document records one dispatch view. Reloading can add another. Repeated submissions of the same receipt count once.
