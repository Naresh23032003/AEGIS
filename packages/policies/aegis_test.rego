# Every OPA rule has an opa test (CLAUDE.md). This one guards the phase 0
# placeholder; delete once the real rules land in phase 3.
package aegis

test_default_deny if {
	not allow
}
