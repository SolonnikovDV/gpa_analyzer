from modules.analysis.nested_block_extractor import extract_nested_sql_blocks


def test_extract_nested_blocks_from_dollar_quoted_function():
    sql = """CREATE OR REPLACE FUNCTION calc_max_date_sum()
RETURNS TABLE(max_date date, sum_value numeric) AS $function$
BEGIN
   RETURN QUERY
   WITH cte AS (
       SELECT MAX(date_column) AS max_date
       FROM source_table
   )
   SELECT c.max_date,
          SUM(st.value1 + st.value2)
   FROM source_table st
   JOIN cte c ON st.date_column = c.max_date
   WHERE st.date_column = c.max_date;
END;
$function$ LANGUAGE plpgsql;"""

    blocks = extract_nested_sql_blocks(sql)

    assert blocks is not None
    assert len(blocks) >= 1
    assert blocks[0].block_type == "CREATE"
