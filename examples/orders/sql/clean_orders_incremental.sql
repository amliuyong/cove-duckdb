-- Named inputs: changes = this committed ODS interval with _cove_operation and
-- _cove_commit_sequence; key_state = the target's _cove_version/_cove_sequence/_cove_deleted.
-- Wire output metadata is kept by the runner, not exposed as business columns.
WITH ranked AS (
    SELECT *, row_number() OVER (
        PARTITION BY order_id ORDER BY source_version DESC, _cove_commit_sequence DESC
    ) AS version_rank
    FROM changes
)
SELECT
    CASE WHEN c._cove_operation = 'delete' THEN 'DELETE' ELSE 'UPSERT' END AS _cove_op,
    c.order_id,
    CASE WHEN c._cove_operation = 'delete' THEN NULL ELSE CAST(c.event_time AS DATE) END AS order_date,
    CASE WHEN c._cove_operation = 'delete' THEN NULL ELSE CAST(c.amount AS DECIMAL(18,2)) END AS amount,
    c.source_version AS _cove_version,
    c._cove_commit_sequence AS _cove_sequence
FROM ranked c
LEFT JOIN key_state s USING (order_id)
WHERE c.version_rank = 1
  AND (s.order_id IS NULL
       OR c.source_version > s._cove_version
       OR (c.source_version = s._cove_version AND c._cove_commit_sequence > s._cove_sequence));
