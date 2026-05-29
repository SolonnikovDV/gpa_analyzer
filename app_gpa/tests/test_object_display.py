from modules.analysis.object_display import resolve_object_display_label

FUNCTION_DDL = """CREATE OR REPLACE FUNCTION calc_max_date_sum()
RETURNS TABLE(max_date date, sum_value numeric) AS $function$
BEGIN
   RETURN QUERY SELECT 1;
END;
$function$ LANGUAGE plpgsql;"""


def test_named_function():
    assert resolve_object_display_label("function", "calc_max_date_sum", FUNCTION_DDL) == "calc_max_date_sum"


def test_named_function_parsed_from_ddl_when_unknown():
    assert resolve_object_display_label("function", "unknown", FUNCTION_DDL) == "calc_max_date_sum"


def test_query():
    assert resolve_object_display_label("query", None, "SELECT * FROM t") == "запрос"


def test_anonymous_do_block():
    ddl = "DO $body$ BEGIN PERFORM 1; END; $body$;"
    assert resolve_object_display_label("function", "unknown", ddl) == "анонимная функция"


def test_anonymous_body_only():
    ddl = "BEGIN\n  RETURN QUERY SELECT 1;\nEND;"
    assert resolve_object_display_label("function", "", ddl) == "анонимная функция"
