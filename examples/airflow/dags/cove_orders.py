"""External orchestration: release downstream work only after Cove publishes."""

from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from cove_operator import CovePipelineRunOperator


def downstream(**context):
    result = context["ti"].xcom_pull(task_ids="cove_orders")
    if result["status"] != "PUBLISHED" or not all(result["releases"].values()):
        raise ValueError("Cove run is not published")
    # A real downstream system would read these exact releases.
    print({"cove_run": result["run_id"], "releases": result["releases"]})


with DAG("cove_orders", start_date=datetime(2026, 10, 1), schedule=None, catchup=False, max_active_runs=1) as dag:
    cove = CovePipelineRunOperator(
        task_id="cove_orders", space_id=Variable.get("cove_space_id", default_var="space"),
        pipeline_id="orders", pipeline_version="{{ var.value.cove_orders_version }}",
        poll_seconds=10, wait_seconds=1800, retries=2)
    release = PythonOperator(task_id="downstream_after_publication", python_callable=downstream)
    cove >> release
