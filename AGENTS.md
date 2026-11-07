# AGENTS.md — AI Agent Collaboration Protocol

> Version: 1.0.0  
> Last Updated: 2026-11-07

---

## Purpose

This document defines the protocol for AI agents (Codex, Qoder, Claude, GPT-4, etc.) collaborating on the Catalyst Knowledge Expert Kit project. It establishes:

1. What agents can and cannot modify
2. How to handle framework vs. domain-specific changes
3. Testing and validation requirements
4. Communication protocols with human experts

---

## Core Principles

### 1. Protect the Framework

**Framework code is sacred.** The following directories contain validated, tested engineering work:

- `src/**` — Core pipeline logic
- `scripts/**` — Execution scripts
- `tests/**` — Test suite
- `config/pipeline*.yaml` — Pipeline configuration

**Agents must NOT modify these files** unless explicitly authorized by the PI (Principal Investigator) to fix a verified framework bug.

### 2. Empower Domain Experts

Domain experts (catalysis researchers) can modify:

- `config/prompts/**` — LLM extraction prompts
- `config/audit_anchors.yaml` — Physical plausibility ranges
- `config/quantity_definitions.yaml` — Unit conversions and validation
- `proposed_schemas/**` — Candidate schema extensions

**Agents should facilitate these modifications** by providing clear documentation, validation, and testing support.

### 3. No Silent Failures

**Every failure must be visible.** Do not suppress errors, mask failures with defaults, or claim success when validation fails.

- If a test fails, report it.
- If data is missing, mark it as missing.
- If a check cannot be performed, say so explicitly.

### 4. Evidence Over Assertion

**Show your work.** Every claim must be backed by:

- File paths and line numbers
- Test output or validation results
- Data provenance (where did this value come from?)

---

## Agent Roles

### Role 1: Framework Guardian

**Responsibilities:**
- Protect `src/`, `scripts/`, `tests/`, `config/pipeline*.yaml`
- Validate that PRs do not modify framework code
- Run regression tests after any change
- Report framework bugs as Issues (do not fix directly)

**When to Act:**
- A PR modifies framework files
- A test fails after a domain expert change
- A domain expert requests a framework modification

**Actions:**
1. Block the PR if framework files are modified without PI approval
2. Run full test suite: `pytest tests/ --cov=src/catalyst_knowledge`
3. If tests fail, identify root cause and report
4. If framework bug is confirmed, create GitHub Issue with label `framework-bug`

### Role 2: Domain Expert Assistant

**Responsibilities:**
- Help domain experts understand prompt/schema structure
- Validate that edits to `config/prompts/`, `config/audit_anchors.yaml`, etc. are syntactically correct
- Run targeted tests to verify changes don't break extraction
- Generate before/after comparisons

**When to Act:**
- A domain expert wants to refine extraction prompts
- A domain expert proposes schema extensions
- A domain expert needs help understanding pipeline behavior

**Actions:**
1. Explain the relevant prompt/schema structure
2. Validate syntax: `python -c "import yaml; yaml.safe_load(open('config/prompts/science_extraction_v2.yaml'))"`
3. Run extraction on a test document to verify behavior
4. Generate a comparison report showing what changed

### Role 3: Test Engineer

**Responsibilities:**
- Maintain test coverage
- Add tests for new features
- Validate that changes don't break existing tests
- Run regression tests before merging PRs

**When to Act:**
- A new feature is added
- A bug is fixed
- A PR is submitted

**Actions:**
1. Run full test suite: `pytest tests/`
2. Check coverage: `pytest tests/ --cov=src/catalyst_knowledge --cov-report=html`
3. If coverage drops, identify untested code paths
4. Add tests for new functionality
5. Validate all tests pass before merging

### Role 4: Documentation Keeper

**Responsibilities:**
- Keep README.md, docs/, and inline comments up to date
- Ensure that changes are reflected in documentation
- Validate that examples still work

**When to Act:**
- A feature is added or changed
- Documentation becomes outdated
- An example breaks

**Actions:**
1. Update relevant documentation files
2. Validate examples still run: `python scripts/generate_html_knowledge_report_v3.py`
3. Check that HTML report opens correctly in browser
4. Update PROMPT_SCHEMA_CATALOG.md if prompts/schemas change

---

## Modification Rules

### ALLOWED Modifications (No PI Approval Required)

| File/Directory | What Can Change | Validation Required |
|----------------|-----------------|---------------------|
| `config/prompts/science_extraction_v2.yaml` | Prompt text, common instructions, extraction parameters | Syntax check + test extraction |
| `config/audit_anchors.yaml` | Plausibility ranges, add/remove quantities | Syntax check |
| `config/quantity_definitions.yaml` | Add quantity types, update conversions, modify validation rules | Syntax check + unit tests |
| `proposed_schemas/*.yaml` | Any changes (these are candidates, not production) | Schema validation |
| `docs/*.md` | Documentation updates | Proofreading |
| `README.md` | Documentation updates | Proofreading |
| `examples/` | Add new examples (do not modify F02 without permission) | Validate example runs |

### CONDITIONAL Modifications (PI Approval Required)

| File/Directory | Condition | Approval Process |
|----------------|-----------|------------------|
| `scripts/generate_html_knowledge_report_v3.py` | Bug fix or enhancement | Submit PR with detailed explanation + before/after screenshots |
| `scripts/run_pipeline.py` | Add new CLI options | Submit PR with usage examples |

### FORBIDDEN Modifications (Framework Code — Never Modify Directly)

| File/Directory | Reason | What to Do Instead |
|----------------|--------|-------------------|
| `src/**` | Core framework logic | Submit GitHub Issue with label `framework-bug` or `framework-enhancement` |
| `scripts/**` (except HTML generator) | Pipeline execution | Submit GitHub Issue |
| `tests/**` | Test suite integrity | Submit GitHub Issue if tests need updating |
| `config/pipeline*.yaml` | Pipeline DAG and stage configuration | Submit GitHub Issue |
| `config/prompts/` (other than science_extraction_v2.yaml) | Other prompts not yet validated | Submit GitHub Issue |

---

## Testing Protocol

### Before Submitting a PR

1. **Syntax Validation**
   ```bash
   # Validate YAML files
   python -c "import yaml; yaml.safe_load(open('config/prompts/science_extraction_v2.yaml'))"
   python -c "import yaml; yaml.safe_load(open('config/audit_anchors.yaml'))"
   python -c "import yaml; yaml.safe_load(open('config/quantity_definitions.yaml'))"
   ```

2. **Run Test Suite**
   ```bash
   pytest tests/ -v
   ```

3. **Check Coverage** (if modifying src/)
   ```bash
   pytest tests/ --cov=src/catalyst_knowledge --cov-report=term-missing
   ```

4. **Validate Example** (if modifying prompts)
   ```bash
   # Re-run F02 extraction with new prompts
   python scripts/run_pipeline.py --config config/pipeline_014_real_e2e_gate.yaml --document-id F02
   python scripts/generate_html_knowledge_report_v3.py
   # Open examples/F02/F02_knowledge_report_v3.html in browser
   ```

### After PR Submission

1. **CI Checks** (automated)
   - Lint: `flake8 src/ scripts/ tests/`
   - Type check: `mypy src/`
   - Tests: `pytest tests/`
   - Coverage: Must not drop below 80%

2. **Human Review**
   - Framework Guardian validates no framework files modified
   - Domain Expert validates scientific accuracy (if prompts changed)
   - Test Engineer validates test coverage

3. **Merge Criteria**
   - All CI checks pass
   - At least 1 human review approval
   - No unresolved comments
   - Documentation updated (if applicable)

---

## Communication Protocol

### Reporting Bugs

**Framework Bugs:**
- Create GitHub Issue with label `framework-bug`
- Include: file path, line number, error message, steps to reproduce
- Do NOT attempt to fix directly

**Domain/Extraction Bugs:**
- Create GitHub Issue with label `extraction-bug`
- Include: document ID, expected vs. actual extraction, prompt version
- May propose fix via PR (if in allowed modification list)

### Requesting Enhancements

**Framework Enhancements:**
- Create GitHub Issue with label `framework-enhancement`
- Describe the use case and why current framework is insufficient
- Wait for PI approval before implementation

**Domain Enhancements:**
- Create GitHub Issue with label `enhancement`
- If in allowed modification list, submit PR directly
- If uncertain, ask in Issue first

### Asking Questions

- Use GitHub Discussions for general questions
- Use Issue comments for specific bug/feature discussions
- Tag relevant agents: `@framework-guardian`, `@domain-expert-assistant`, `@test-engineer`

---

## Validation Checklist

Before marking a task as complete, verify:

- [ ] No framework files modified (unless PI-approved)
- [ ] All YAML files pass syntax validation
- [ ] Test suite passes: `pytest tests/`
- [ ] Coverage ≥ 80% (if src/ modified)
- [ ] Example still runs (if prompts modified)
- [ ] Documentation updated (if behavior changed)
- [ ] PR description explains what changed and why
- [ ] No sensitive data committed (API keys, credentials)
- [ ] .gitignore respected (no large files, no caches)

---

## Emergency Procedures

### If Framework Code is Accidentally Modified

1. **Stop**: Do not commit or push
2. **Revert**: `git checkout -- <file>`
3. **Assess**: Determine if change was necessary
4. **Route**: If necessary, create GitHub Issue for PI review
5. **Document**: Add note to PR explaining the revert

### If Tests Fail After Domain Expert Change

1. **Isolate**: Identify which test(s) failed
2. **Diagnose**: Determine if failure is due to:
   - Syntax error in modified file → Fix syntax
   - Behavioral change in extraction → Validate with domain expert
   - Framework bug exposed by change → Create GitHub Issue
3. **Fix or Escalate**: Fix if in allowed scope, otherwise escalate
4. **Re-test**: Validate fix resolves the failure
5. **Document**: Update PR with explanation

### If a PR is Blocked by Framework Guardian

1. **Review**: Read the block reason carefully
2. **Discuss**: Ask questions in PR comments if unclear
3. **Revise**: Make requested changes
4. **Re-submit**: Push updates and request re-review
5. **Escalate**: If disagreement persists, request PI arbitration

---

## Agent-Specific Notes

### For Codex / Qoder

- You have access to the full codebase
- Use `SearchWorkspace` for code discovery
- Use `Agent` with `subagent_type=Explore` for deep dives
- Validate changes with `pytest` before committing
- Never commit API keys or large files

### For Claude / GPT-4 (via API)

- You may not have direct file access
- Provide code snippets and explanations
- Human collaborator will apply changes
- Validate syntax in your responses
- Be explicit about which files to modify

### For Human Domain Experts

- You know the science — we know the engineering
- Tell us what you want to extract, not how to code it
- We'll help you express it in prompts/schemas
- Test your changes on real documents
- Ask questions — we're here to help

---

## Version Control

### Branch Naming

- `feature/<description>` — New features
- `fix/<description>` — Bug fixes
- `docs/<description>` — Documentation updates
- `refactor/<description>` — Code refactoring (framework only)
- `test/<description>` — Test additions

### Commit Messages

Format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation
- `style` — Formatting (no code change)
- `refactor` — Code restructuring
- `test` — Adding tests
- `chore` — Maintenance

Examples:
```
feat(prompts): Add selectivity extraction guidance

Include specific instructions for extracting selectivity values
with units and conditions. Addresses Issue #42.
```

```
fix(schema): Correct unit conversion for activation energy

Was using kJ/mol but schema expects J/mol. Added conversion
factor in quantity_definitions.yaml.
```

---

## Success Metrics

### For Domain Expert Contributions

- ✅ Prompt changes improve extraction accuracy (validated on test docs)
- ✅ New quantity types are correctly normalized
- ✅ Schema proposals are adopted into production
- ✅ HTML reports reflect improved scientific content

### For Framework Maintenance

- ✅ Zero unauthorized framework modifications
- ✅ 100% test pass rate
- ✅ ≥80% code coverage
- ✅ All framework bugs tracked via Issues
- ✅ Documentation stays current

---

## Contact

- **PI / Framework Owner**: Jinhui Zhao
- **Repository**: https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit
- **Issues**: https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit/issues
- **Discussions**: https://github.com/JinhZhao/Catalyst-Knowledge-Expert-Kit/discussions

---

**Last Updated**: 2026-11-07  
**Version**: 1.0.0  
**Status**: ✅ Active
