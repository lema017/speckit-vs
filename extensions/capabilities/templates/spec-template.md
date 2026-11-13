# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft

**Input**: User description: "$ARGUMENTS"

## Slice *(mandatory)*

<!--
  ACTION REQUIRED: One spec builds one slice: one thing a person can do and check from end to end.
  If "SLICE FOR THIS RUN" appears earlier in this run, copy its two lines here in place of the two below.
  If this spec is a slice on its own, name the one outcome:

      - Slice: standalone — <what a person can do and check when this spec is done>

  Out lists what the request also asked for and other slices build. Write "none" when there is nothing.
-->

- Slice: [slice id from specs/_slices/, or: standalone — <what a person can do and check>]
- Out: [what other slices build, each with its slice id, or: none]

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: This spec is ONE slice, so it holds ONE user story: a journey a person can test and
  see working on its own. If the request holds more, the others belong to other slices: name them in
  "Out" under "## Slice" and do not write them here.

  Write a second story only when it cannot be delivered or tested apart from the first, and say why
  in its "Why this priority" line.
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the feature description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]

## Capability Delta *(mandatory)*

<!-- capability-delta:v1 -->
<!--
  ACTION REQUIRED: Declare which approved rules this change adds, modifies or removes.
  The catalog at specs/_capabilities/ holds the current text. Copy From literally.

    ### MODIFIED R-session-expiry
    - Capability: login
    - From: <current text, literal>
    - To: <new text, one sentence>
    - Links: FR-003, US1/AC2

  ADDED uses "From: (none)". REMOVED uses "To: (none)" and "Replaced-By: <rule id or none>".
  A rule marked [designed] is approved and not built: build it with IMPLEMENTED, with the
  catalog's text in both From and To. review writes the catalog's text there and says so.

    ### IMPLEMENTED R-login-lockout
    - Capability: login
    - From: <the [designed] rule's text, literal>
    - To: <the same text>
    - Links: FR-007

  A new capability also needs "### NEW-CAPABILITY <name>" with "- Covers: <business language>".
  If no rule changes, write one line instead: Capabilities: none — <reason>
  Keep this block as is. The headings above are examples and do not count.
-->
