SELECT o.order_date,
       CAST(sum(o.amount) AS DECIMAL(38,2)) AS revenue,
       CAST(count(*) AS BIGINT) AS order_count,
       CAST(sum(CASE WHEN s.high_value THEN 1 ELSE 0 END) AS BIGINT) AS high_value_count
FROM orders AS o
JOIN scores AS s ON o.order_id = s.order_id
GROUP BY o.order_date;
