# NutriBrain Coding Style Guide

This guide is prescriptive. If a rule here conflicts with implementation convenience, follow the rule.

## 1. Layering

### 1.1 Domain layer is the product
- Put business rules in `api/app/domain/` only.
- Domain functions:
  - accept primitives and typed DTOs
  - return typed DTOs
  - raise domain exceptions
- Domain code must not import FastAPI, FastMCP, or route/tool transport helpers.
- Domain code may depend on an injected SQLAlchemy session for persistence boundaries, but must not own session lifecycle management.

### 1.2 Adapters stay thin
- FastAPI routes in `api/app/api/` translate HTTP payloads to domain calls and domain results back to response DTOs.
- MCP tools in `api/app/mcp/` translate tool args to the same domain calls.
- No business branching logic in routes or MCP tools.

## 2. Naming

### 2.1 Python
- Use `snake_case` for functions, variables, and module-level names.
- Use verb-first names for domain operations: `log_meal`, `resolve_food`, `compute_effective_target`.
- Class names remain `PascalCase`.

### 2.2 TypeScript
- Use `camelCase` for variables, functions, and parameters.
- Use `PascalCase` for types, interfaces, and React components.
- Use `UPPER_CASE` for constants where appropriate.

## 3. Errors

- Use one exception hierarchy rooted at `DomainError`.
- Each domain exception must carry an Appendix C `error` code.
- Do not raise `HTTPException` in domain code.
- Outside the error-handler module, do not throw transport-specific exceptions as control flow for business rules.

## 4. Numeric rules for nutrition math

- Python domain math uses `Decimal` for macros and quantity-derived calculations.
- Do not use `float` in domain nutrition calculations.
- Frontend uses `number` for display and charting.
- Do not round during domain computation.
- Round only at final serialization/display boundaries:
  - grams: 1 decimal place
  - calories: whole numbers

## 5. Dates and timezones

- Persist timestamps in UTC.
- Persist IANA timezone names with meals (`local_tz`).
- Compute and persist `local_date` at write time in backend domain logic.
- Never call `datetime.now()` without a timezone.
- Frontend must never derive local day from UTC timestamps for business views; use API-provided `local_date`.

## 6. Nullability invariants

- `meal_items.food_id IS NULL` means ad-hoc estimate.
- Macros on a `meal_item` are populated if and only if `food_id IS NULL`.
- Enforce this invariant in both:
  - database constraints
  - domain validation

## 7. Testing expectations

- Domain-first tests:
  - use pure unit tests when DB is not required
  - use transactional DB fixture when persistence behavior is under test
- Route tests:
  - one happy path and one representative error path per route
- Frontend tests:
  - focus on state transitions, query/mutation behavior, and form behavior
  - do not spend test budget snapshot-testing chart internals

## 8. Commits

- Use Conventional Commits.
- Subject lines in imperative mood.
- One logical change per commit.

## 9. Comments

- Add comments for propagation rules and non-obvious business decisions.
- Avoid narrating obvious code.
- Prefer clear names and short helpers over explanatory comment blocks.

## 10. Enforcement matrix

Rules below are enforced by tooling and must stay enabled.

### 10.1 Python
- Ruff naming rules (`N`) enforce Python naming conventions.
- Ruff datetime rules (`DTZ`) enforce timezone-safe datetime usage.
- Mypy strict mode for `api/app/domain/**` enforces stronger type discipline where business logic lives.

### 10.2 TypeScript
- TypeScript strict compiler options enforce type safety (`strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`).
- ESLint naming convention rules enforce `camelCase` variables/parameters and `PascalCase` type-like names.
- `eslint-plugin-jsx-a11y` enforces baseline accessibility standards for UI code.

### 10.3 Not mechanically enforced (review required)
- Domain-only business logic placement.
- Domain exception taxonomy and Appendix C code completeness.
- Decimal-only nutrition math semantics where type declarations are incomplete.
- Mutation-propagation rules from the spec.
- Commit message format and scope.
