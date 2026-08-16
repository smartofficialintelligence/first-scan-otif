{# Use the configured schema as the BigQuery dataset id (matches Terraform).
   Default dbt behavior would create olist_dbt_staging etc.; we want staging/intermediate/ml. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
