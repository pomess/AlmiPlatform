# Databricks notebook source
# MAGIC %md
# MAGIC # Platinum Layer — Refresh Job
# MAGIC
# MAGIC Populates all `platinum_*` tables from the existing Gold layer.
# MAGIC Schedule: daily at 06:00 UTC via Lakeflow Job.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StringType
import hashlib

catalog = spark.conf.get("atlas.catalog", "dev_gold_commercial")
schema = "genai_mcm_d360"

def full_table(name: str) -> str:
    return f"{catalog}.{schema}.{name}"

def deterministic_id(node_type: str, name: str) -> str:
    return hashlib.md5(f"{node_type}||{name}".lower().encode()).hexdigest()

deterministic_id_udf = F.udf(deterministic_id, StringType())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Populate platinum_graph_nodes

# COMMAND ----------

from pyspark.sql import DataFrame
from functools import reduce

def union_all(dfs: list) -> DataFrame:
    return reduce(DataFrame.unionByName, dfs, allowMissingColumns=True)

# Companies from globaldata_companies_metadata
companies = (
    spark.table(full_table("globaldata_companies_metadata"))
    .select(
        F.lit("company").alias("node_type"),
        F.col("company_name").alias("name"),
        F.array(F.col("company_name")).alias("aliases"),
        F.create_map(
            F.lit("hq_country"), F.col("hq_country"),
            F.lit("revenue"), F.col("revenue").cast("string"),
        ).alias("properties"),
        F.array(F.lit("globaldata_companies_metadata")).alias("source_tables"),
    )
    .dropDuplicates(["name"])
)

# Drugs from pipeline + marketed
pipeline_drugs = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .select(
        F.lit("drug").alias("node_type"),
        F.col("drug_name").alias("name"),
        F.array(F.col("drug_name")).alias("aliases"),
        F.create_map(
            F.lit("phase"), F.col("highest_phase"),
            F.lit("mechanism"), F.col("mechanism_of_action"),
            F.lit("developer"), F.col("company_name"),
        ).alias("properties"),
        F.array(F.lit("globaldata_pipelinedrugs_metadata")).alias("source_tables"),
    )
    .dropDuplicates(["name"])
)

marketed_drugs = (
    spark.table(full_table("globaldata_marketeddrugs_metadata"))
    .select(
        F.lit("drug").alias("node_type"),
        F.col("drug_name").alias("name"),
        F.array(F.col("drug_name")).alias("aliases"),
        F.create_map(
            F.lit("phase"), F.lit("Approved"),
            F.lit("mechanism"), F.col("mechanism_of_action"),
            F.lit("developer"), F.col("company_name"),
        ).alias("properties"),
        F.array(F.lit("globaldata_marketeddrugs_metadata")).alias("source_tables"),
    )
    .dropDuplicates(["name"])
)

# Indications (extracted from pipeline + marketed drug indications)
indications_pipeline = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .select(F.explode(F.split(F.col("indication"), ";")).alias("name"))
    .select(
        F.lit("indication").alias("node_type"),
        F.trim(F.col("name")).alias("name"),
        F.array(F.trim(F.col("name"))).alias("aliases"),
        F.create_map().cast("map<string,string>").alias("properties"),
        F.array(F.lit("globaldata_pipelinedrugs_metadata")).alias("source_tables"),
    )
    .dropDuplicates(["name"])
)

# KOLs from minutes metadata
kols = (
    spark.table(full_table("all_kol_minutes_metadata"))
    .select(
        F.lit("kol").alias("node_type"),
        F.col("speaker_name").alias("name"),
        F.array(F.col("speaker_name")).alias("aliases"),
        F.create_map(
            F.lit("institution"), F.col("institution"),
            F.lit("disease_area"), F.col("disease_area"),
        ).alias("properties"),
        F.array(F.lit("all_kol_minutes_metadata")).alias("source_tables"),
    )
    .filter(F.col("speaker_name").isNotNull())
    .dropDuplicates(["name"])
)

# Union all node types
all_nodes = union_all([companies, pipeline_drugs, marketed_drugs, indications_pipeline, kols])

# Add deterministic node_id and timestamp
nodes_final = (
    all_nodes
    .withColumn("node_id", deterministic_id_udf(F.col("node_type"), F.col("name")))
    .withColumn("updated_at", F.current_timestamp())
    .select("node_id", "node_type", "name", "aliases", "properties", "source_tables", "updated_at")
)

nodes_final.write.mode("overwrite").saveAsTable(full_table("platinum_graph_nodes"))
print(f"✓ platinum_graph_nodes: {nodes_final.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Populate platinum_graph_edges

# COMMAND ----------

import uuid

# Company → develops → Drug (from pipeline)
develops_edges = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .select(
        deterministic_id_udf(F.lit("company"), F.col("company_name")).alias("source_node"),
        deterministic_id_udf(F.lit("drug"), F.col("drug_name")).alias("target_node"),
        F.lit("develops").alias("relation_type"),
        F.lit(1.0).cast("float").alias("confidence"),
        F.array(F.lit("globaldata_pipelinedrugs_metadata")).alias("evidence_sources"),
        F.create_map(
            F.lit("phase"), F.col("highest_phase"),
        ).alias("properties"),
    )
    .dropDuplicates(["source_node", "target_node"])
)

# Drug → treats → Indication (from pipeline)
treats_edges = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .select(
        F.col("drug_name"),
        F.explode(F.split(F.col("indication"), ";")).alias("indication_raw"),
    )
    .select(
        deterministic_id_udf(F.lit("drug"), F.col("drug_name")).alias("source_node"),
        deterministic_id_udf(F.lit("indication"), F.trim(F.col("indication_raw"))).alias("target_node"),
        F.lit("treats").alias("relation_type"),
        F.lit(1.0).cast("float").alias("confidence"),
        F.array(F.lit("globaldata_pipelinedrugs_metadata")).alias("evidence_sources"),
        F.create_map().cast("map<string,string>").alias("properties"),
    )
    .dropDuplicates(["source_node", "target_node"])
)

# Company → sponsors_trial → Trial (from clinical_trials_metadata)
sponsors_edges = (
    spark.table(full_table("clinical_trials_metadata"))
    .filter(F.col("lead_sponsor").isNotNull())
    .select(
        deterministic_id_udf(F.lit("company"), F.col("lead_sponsor")).alias("source_node"),
        deterministic_id_udf(F.lit("trial"), F.col("nct_id")).alias("target_node"),
        F.lit("sponsors_trial").alias("relation_type"),
        F.lit(1.0).cast("float").alias("confidence"),
        F.array(F.lit("clinical_trials_metadata")).alias("evidence_sources"),
        F.create_map().cast("map<string,string>").alias("properties"),
    )
    .dropDuplicates(["source_node", "target_node"])
)

all_edges = union_all([develops_edges, treats_edges, sponsors_edges])

edges_final = (
    all_edges
    .withColumn("edge_id", F.expr("uuid()"))
    .withColumn("updated_at", F.current_timestamp())
    .select("edge_id", "source_node", "target_node", "relation_type", "confidence", "evidence_sources", "properties", "updated_at")
)

edges_final.write.mode("overwrite").saveAsTable(full_table("platinum_graph_edges"))
print(f"✓ platinum_graph_edges: {edges_final.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Populate platinum_news_events

# COMMAND ----------

# From GlobalData news
news_events = (
    spark.table(full_table("globaldata_news_metadata"))
    .select(
        F.expr("uuid()").alias("event_id"),
        F.col("published_date").cast("date").alias("event_date"),
        F.lit("globaldata_news").alias("source"),
        F.lit("news").alias("category"),
        F.col("title"),
        F.col("summary"),
        F.col("url"),
        F.lit(None).cast("array<struct<name:string,type:string,node_id:string>>").alias("entities"),
        F.lit(None).cast("float").alias("relevance_score"),
        F.lit(None).cast("string").alias("sentiment"),
        F.lit(None).cast("array<string>").alias("tags"),
        F.current_timestamp().alias("ingested_at"),
    )
    .filter(F.col("event_date").isNotNull())
)

# From GlobalData catalysts
catalysts = (
    spark.table(full_table("globaldata_catalyst_metadata"))
    .select(
        F.expr("uuid()").alias("event_id"),
        F.col("expected_date").cast("date").alias("event_date"),
        F.lit("globaldata_catalysts").alias("source"),
        F.lit("catalyst").alias("category"),
        F.col("catalyst_type").alias("title"),
        F.col("description").alias("summary"),
        F.lit(None).cast("string").alias("url"),
        F.lit(None).cast("array<struct<name:string,type:string,node_id:string>>").alias("entities"),
        F.lit(None).cast("float").alias("relevance_score"),
        F.lit(None).cast("string").alias("sentiment"),
        F.lit(None).cast("array<string>").alias("tags"),
        F.current_timestamp().alias("ingested_at"),
    )
    .filter(F.col("event_date").isNotNull())
)

all_events = news_events.unionByName(catalysts, allowMissingColumns=True)
all_events.write.mode("overwrite").saveAsTable(full_table("platinum_news_events"))
print(f"✓ platinum_news_events: {all_events.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Populate platinum_bullseye

# COMMAND ----------

# Almirall drugs (ring 1)
almirall_drugs = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .filter(F.lower(F.col("company_name")).contains("almirall"))
)

almirall_indications = [row.indication for row in almirall_drugs.select("indication").distinct().collect()]

# All pipeline drugs with ring assignment
bullseye = (
    spark.table(full_table("globaldata_pipelinedrugs_metadata"))
    .select(
        deterministic_id_udf(F.lit("drug"), F.col("drug_name")).alias("entity_id"),
        F.col("drug_name").alias("entity_name"),
        F.lit("drug").alias("entity_type"),
        F.when(F.lower(F.col("company_name")).contains("almirall"), 1)
         .when(F.col("indication").isin(almirall_indications), 2)
         .otherwise(3)
         .alias("ring"),
        F.split(F.col("indication"), ";").getItem(0).alias("segment"),
        F.lit(None).cast("float").alias("threat_score"),
        F.lit(None).cast("float").alias("opportunity_score"),
        F.array(
            F.struct(
                F.col("drug_name").alias("drug"),
                F.col("highest_phase").alias("phase"),
                F.split(F.col("indication"), ";").getItem(0).alias("indication"),
            )
        ).alias("pipeline_summary"),
        F.lit(None).cast("struct<date:date,title:string,category:string>").alias("last_event"),
        F.current_timestamp().alias("updated_at"),
    )
)

bullseye.write.mode("overwrite").saveAsTable(full_table("platinum_bullseye"))
print(f"✓ platinum_bullseye: {bullseye.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Populate platinum_kols

# COMMAND ----------

kol_profiles = (
    spark.table(full_table("all_kol_minutes_metadata"))
    .filter(F.col("speaker_name").isNotNull())
    .groupBy("speaker_name")
    .agg(
        F.first("institution").alias("institution"),
        F.first("country").alias("country"),
        F.collect_set("disease_area").alias("specialties"),
        F.count("*").alias("minutes_count"),
        F.collect_list("topic").alias("recent_topics_raw"),
    )
    .select(
        deterministic_id_udf(F.lit("kol"), F.col("speaker_name")).alias("kol_id"),
        F.col("speaker_name").alias("name"),
        F.col("institution"),
        F.col("country"),
        F.col("specialties"),
        F.lit(None).cast("int").alias("trials_involved"),
        F.col("minutes_count"),
        (F.col("minutes_count") * 0.1).cast("float").alias("influence_score"),
        F.slice(F.col("recent_topics_raw"), 1, 5).alias("recent_topics"),
        F.current_timestamp().alias("updated_at"),
    )
)

kol_profiles.write.mode("overwrite").saveAsTable(full_table("platinum_kols"))
print(f"✓ platinum_kols: {kol_profiles.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Populate platinum_trials

# COMMAND ----------

trials = (
    spark.table(full_table("clinical_trials_metadata"))
    .select(
        F.col("nct_id"),
        F.col("brief_title").alias("title"),
        F.col("overall_status").alias("status"),
        F.col("phase"),
        F.col("lead_sponsor").alias("sponsor"),
        deterministic_id_udf(F.lit("company"), F.col("lead_sponsor")).alias("sponsor_node_id"),
        F.array(F.col("condition")).alias("indications"),
        F.lit(None).cast("array<struct<name:string,node_id:string>>").alias("drugs"),
        F.col("start_date").cast("date").alias("start_date"),
        F.col("primary_completion_date").cast("date").alias("primary_completion_date"),
        F.col("enrollment").cast("int").alias("enrollment"),
        F.lit(None).cast("float").alias("relevance_to_almirall"),
        F.current_timestamp().alias("updated_at"),
    )
)

trials.write.mode("overwrite").saveAsTable(full_table("platinum_trials"))
print(f"✓ platinum_trials: {trials.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

for t in ["platinum_graph_nodes", "platinum_graph_edges", "platinum_news_events", "platinum_bullseye", "platinum_kols", "platinum_trials"]:
    count = spark.table(full_table(t)).count()
    print(f"  {t}: {count:,} rows")
