-- Fail-closed AI view derived from the measured field decisions.
-- Personal retained fields stay blocked here until an OPF transform is enforced.
CREATE VIEW support_tickets_ai_view AS
SELECT
    issue_description
FROM support_tickets;
