do $$
declare t timestamptz := '2026-11-26T12:36:00Z';
begin
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[]}',t)='ready';
  assert monitor_scheduler.source_audit_decision('{}',t)='invalid GitHub preflight';
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[{"name":"Daily government communications","status":"in_progress"}]}',t)='government pipeline busy';
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[{"name":"Government full-source audit","status":"completed","conclusion":"failure","created_at":"2026-11-26T12:20:00Z"}]}',t)='recent audit exists';
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[{"name":"Dependency update","status":"in_progress"}]}',t)='ready';
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[]}','2026-11-26T13:36:00Z')='regular collection imminent';
  assert monitor_scheduler.source_audit_decision('{"workflow_runs":[]}','2027-06-01T06:36:00Z')='regular collection imminent';
end $$;
