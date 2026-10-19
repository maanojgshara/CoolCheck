# Databricks notebook source
# DNS reachability check from serverless: one line per host. Prints no keys or tokens.

# COMMAND ----------

import socket

HOSTS = [
    "api-open.data.gov.sg",
    "data.gov.sg",
    "api.data.gov.sg",
    "www.onemap.gov.sg",
    "www.weather.gov.sg",
    "www.ema.gov.sg",
    "pypi.org",
    "github.com",
    "raw.githubusercontent.com",
    "google.com",
]

for host in HOSTS:
    try:
        socket.getaddrinfo(host, 443)
        print(f"{host}: resolves")
    except Exception as e:
        print(f"{host}: BLOCKED ({type(e).__name__})")
