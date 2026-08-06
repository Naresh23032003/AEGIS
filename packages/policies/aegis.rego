# plan/03-agents-and-policy.md, OPA policy. Package aegis.actions, entry
# `decision` returning {allow, rule_id, reason}. The worker (aegis.policy)
# calls this over HTTP for every proposal and emits action.policy_checked
# with rule_id either way, allow or deny.
#
# Six rules, evaluated in priority order via the else-chain below:
#   1. deny if catalog_key not in the closed catalog (defense in depth;
#      the executor checks this independently again before it ever runs
#      a command, per plan/04-security.md, Executor sandbox).
#   2. deny if confidence < 0.6.
#   3. deny if incident.actions_executed >= 5 (runaway brake).
#   4. deny red tier when severity is sev3 (risk exceeds impact).
#   5. deny scale_service if already scaled (params.already_scaled, set
#      by the caller from the actions table, not trusted from the model).
#   6. default deny; allow only via an explicit per-tier rule.
package aegis.actions

# Mirrors apps/core/aegis/actions/catalog.yaml's key set. Kept as a second,
# independent copy on purpose (defense in depth): OPA has no access to the
# Python-side YAML loader, and the point of this rule is that policy denies
# an unknown key even if every other layer somehow let it through.
valid_catalog_keys := {
	"restart_service",
	"clear_cache",
	"remove_toxic",
	"restart_dependency",
	"scale_service",
	"rollback_config",
	"flush_queue",
	"restart_database",
}

min_confidence := 0.6

max_actions_executed := 5

decision := {"allow": false, "rule_id": "deny_unknown_catalog_key", "reason": reason} if {
	not (input.action.catalog_key in valid_catalog_keys)
	reason := sprintf("catalog_key %q is not in the closed action catalog", [input.action.catalog_key])
} else := {"allow": false, "rule_id": "deny_low_confidence", "reason": reason} if {
	input.action.confidence < min_confidence
	reason := sprintf(
		"confidence %.2f is below the minimum %.2f",
		[input.action.confidence, min_confidence],
	)
} else := {"allow": false, "rule_id": "deny_runaway_brake", "reason": reason} if {
	input.incident.actions_executed >= max_actions_executed
	reason := sprintf(
		"incident has already executed %d actions, at the runaway brake of %d",
		[input.incident.actions_executed, max_actions_executed],
	)
} else := {"allow": false, "rule_id": "deny_red_low_severity", "reason": reason} if {
	input.action.tier == "red"
	input.incident.severity == "sev3"
	reason := "red tier denied: severity sev3 does not justify the risk"
} else := {"allow": false, "rule_id": "deny_scale_already_scaled", "reason": reason} if {
	input.action.catalog_key == "scale_service"
	input.action.params.already_scaled == true
	reason := "scale_service denied: target is already scaled"
} else := {"allow": true, "rule_id": "allow_green_tier", "reason": reason} if {
	input.action.tier == "green"
	reason := "green tier auto-executes once no deny rule matches"
} else := {"allow": true, "rule_id": "allow_yellow_tier", "reason": reason} if {
	input.action.tier == "yellow"
	reason := "yellow tier allowed, subject to the veto window"
} else := {"allow": true, "rule_id": "allow_red_tier", "reason": reason} if {
	input.action.tier == "red"
	reason := "red tier allowed, subject to signed approval"
} else := {"allow": false, "rule_id": "default_deny", "reason": "no explicit allow rule matched for this tier"}
