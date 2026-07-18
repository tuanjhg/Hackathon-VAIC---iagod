-- Verify row counts for all 14 catalog tables.
WITH table_counts AS (
    SELECT 'refrigerators' AS table_name, 1692::BIGINT AS expected, COUNT(*) AS product_count FROM refrigerators
    UNION ALL
    SELECT 'air_conditioners', 1039, COUNT(*) FROM air_conditioners
    UNION ALL
    SELECT 'washing_machines', 1337, COUNT(*) FROM washing_machines
    UNION ALL
    SELECT 'clothes_dryers', 107, COUNT(*) FROM clothes_dryers
    UNION ALL
    SELECT 'dishwashers', 134, COUNT(*) FROM dishwashers
    UNION ALL
    SELECT 'coolers_freezers', 222, COUNT(*) FROM coolers_freezers
    UNION ALL
    SELECT 'water_heaters', 319, COUNT(*) FROM water_heaters
    UNION ALL
    SELECT 'karaoke_microphones', 37, COUNT(*) FROM karaoke_microphones
    UNION ALL
    SELECT 'phone_recording_microphones', 33, COUNT(*) FROM phone_recording_microphones
    UNION ALL
    SELECT 'smartwatches', 1336, COUNT(*) FROM smartwatches
    UNION ALL
    SELECT 'desktop_computers', 405, COUNT(*) FROM desktop_computers
    UNION ALL
    SELECT 'computer_monitors', 469, COUNT(*) FROM computer_monitors
    UNION ALL
    SELECT 'printers', 147, COUNT(*) FROM printers
    UNION ALL
    SELECT 'tablets', 1469, COUNT(*) FROM tablets
)
SELECT
    table_name,
    expected,
    product_count,
    product_count - expected AS difference,
    CASE WHEN product_count = expected THEN 'OK' ELSE 'MISMATCH' END AS status
FROM table_counts
UNION ALL
SELECT
    'TOTAL',
    SUM(expected),
    SUM(product_count),
    SUM(product_count) - SUM(expected),
    CASE WHEN SUM(product_count) = SUM(expected) THEN 'OK' ELSE 'MISMATCH' END
FROM table_counts
ORDER BY table_name;

-- Compact grand total only.
SELECT
    (SELECT COUNT(*) FROM refrigerators)
  + (SELECT COUNT(*) FROM air_conditioners)
  + (SELECT COUNT(*) FROM washing_machines)
  + (SELECT COUNT(*) FROM clothes_dryers)
  + (SELECT COUNT(*) FROM dishwashers)
  + (SELECT COUNT(*) FROM coolers_freezers)
  + (SELECT COUNT(*) FROM water_heaters)
  + (SELECT COUNT(*) FROM karaoke_microphones)
  + (SELECT COUNT(*) FROM phone_recording_microphones)
  + (SELECT COUNT(*) FROM smartwatches)
  + (SELECT COUNT(*) FROM desktop_computers)
  + (SELECT COUNT(*) FROM computer_monitors)
  + (SELECT COUNT(*) FROM printers)
  + (SELECT COUNT(*) FROM tablets) AS total_products;
