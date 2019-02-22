#!/usr/bin/env spark-submit
from __future__ import print_function
import argparse
import json
import os

from pyspark import SparkConf, SparkContext, StorageLevel
from pyspark.sql import SparkSession, Column
from pyspark.sql.functions import col
import pyspark.sql.functions as fn
import pyspark.sql.types as types

# stolen from CMSSpark
import schemas

def run(args):
    conf = SparkConf().setMaster("yarn").setAppName("CMS Working Set")
    sc = SparkContext(conf=conf)
    spark = SparkSession(sc)
    print("Initiated spark session on yarn, web URL: http://ithdp1101.cern.ch:8088/proxy/%s" % sc.applicationId)

    avroreader = spark.read.format("com.databricks.spark.avro")
    csvreader = spark.read.format("com.databricks.spark.csv").option("nullValue","null").option("mode", "FAILFAST")

    jobreports = avroreader.load("/project/awg/cms/jm-data-popularity/avro-snappy/year=201[678]/month=*/day=*/*.avro")
    dbs_files = csvreader.schema(schemas.schema_files()).load("/project/awg/cms/CMS_DBS3_PROD_GLOBAL/current/FILES/part-m-00000")
    dbs_blocks = csvreader.schema(schemas.schema_blocks()).load("/project/awg/cms/CMS_DBS3_PROD_GLOBAL/current/BLOCKS/part-m-00000")
    dbs_datasets = csvreader.schema(schemas.schema_datasets()).load("/project/awg/cms/CMS_DBS3_PROD_GLOBAL/current/DATASETS/part-m-00000")

    working_set_day = (jobreports
            .filter((col('JobExecExitTimeStamp')>0) & (col('JobExecExitCode')==0))
            .replace('//', '/', 'FileName')
            .join(dbs_files, col('FileName')==col('f_logical_file_name'))
            .join(dbs_blocks, col('f_block_id')==col('b_block_id'))
            .join(dbs_datasets, col('f_dataset_id')==col('d_dataset_id'))
            .withColumn('day', (col('JobExecExitTimeStamp')-col('JobExecExitTimeStamp')%fn.lit(86400000))/fn.lit(1000))
            .withColumn('input_campaign', fn.regexp_extract(col('d_dataset'), "^/[^/]*/(\w+)-", 1))
            .groupBy('day', 'SubmissionTool', 'input_campaign', 'd_data_tier_id', 'SiteName')
            .agg(
                fn.collect_set('b_block_id').alias('working_set_blocks'),
                fn.sum('WrapCPU').alias('sum_WrapCPU'),
                fn.sum('WrapWC').alias('sum_WrapWC'),
                fn.count('WrapWC').alias('njobs'),
            )
        )

    working_set_day.write.parquet(args.out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=
            "Computes working set (unique blocks accessed) per day, partitioned by various fields."
            "Please run prefixed with `spark-submit --packages com.databricks:spark-avro_2.11:4.0.0`"
            )
    defpath = "hdfs://analytix/user/ncsmith/working_set_day"
    parser.add_argument("--out", metavar="OUTPUT", help="Output path in HDFS for result (default: %s)" % defpath, default=defpath)

    args = parser.parse_args()
    run(args)
