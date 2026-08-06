# Every OPA rule has an opa test (CLAUDE.md). One test per rule in
# aegis.rego's else-chain, plus the three per-tier allows and the final
# catchall, so all six numbered rules in plan/03-agents-and-policy.md are
# exercised by name.
package aegis.actions

base_action := {"catalog_key": "restart_service", "params": {}, "tier": "green", "confidence": 0.9}

base_incident := {"severity": "sev2", "loop_count": 0, "actions_executed": 0}

base_context := {"env": "demo"}

test_deny_unknown_catalog_key if {
	result := decision with input as {
		"action": object.union(base_action, {"catalog_key": "delete_everything"}),
		"incident": base_incident,
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "deny_unknown_catalog_key"
}

test_deny_low_confidence if {
	result := decision with input as {
		"action": object.union(base_action, {"confidence": 0.4}),
		"incident": base_incident,
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "deny_low_confidence"
}

test_deny_runaway_brake if {
	result := decision with input as {
		"action": base_action,
		"incident": object.union(base_incident, {"actions_executed": 5}),
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "deny_runaway_brake"
}

test_deny_red_low_severity if {
	result := decision with input as {
		"action": object.union(base_action, {"tier": "red", "catalog_key": "restart_database"}),
		"incident": object.union(base_incident, {"severity": "sev3"}),
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "deny_red_low_severity"
}

test_deny_scale_already_scaled if {
	result := decision with input as {
		"action": object.union(base_action, {
			"catalog_key": "scale_service",
			"tier": "yellow",
			"params": {"service": "target-orders", "replicas": 2, "already_scaled": true},
		}),
		"incident": base_incident,
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "deny_scale_already_scaled"
}

test_allow_green_tier if {
	result := decision with input as {"action": base_action, "incident": base_incident, "context": base_context}
	result.allow == true
	result.rule_id == "allow_green_tier"
}

test_allow_yellow_tier if {
	result := decision with input as {
		"action": object.union(base_action, {"tier": "yellow", "catalog_key": "restart_dependency"}),
		"incident": base_incident,
		"context": base_context,
	}
	result.allow == true
	result.rule_id == "allow_yellow_tier"
}

test_allow_red_tier if {
	result := decision with input as {
		"action": object.union(base_action, {"tier": "red", "catalog_key": "restart_database"}),
		"incident": object.union(base_incident, {"severity": "sev1"}),
		"context": base_context,
	}
	result.allow == true
	result.rule_id == "allow_red_tier"
}

test_default_deny_unknown_tier if {
	result := decision with input as {
		"action": object.union(base_action, {"tier": "blue"}),
		"incident": base_incident,
		"context": base_context,
	}
	result.allow == false
	result.rule_id == "default_deny"
}
