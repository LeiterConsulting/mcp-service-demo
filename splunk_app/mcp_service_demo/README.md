# MCP Service Demo companion app

This Splunk app creates the `mcp_demo` index and supplies the source type, macros, saved
searches, and dashboard used by the MCP Service Demo. It contains no credentials or event data.

Install the packaged `.tar.gz` from **Apps → Manage Apps → Install app from file**, then restart
Splunk if prompted. An administrator can inspect the **MCP Service Demo** dashboard after the
scenario loader publishes a run through HTTP Event Collector (HEC).

The demo process needs:

- permission to send events to the `mcp_demo` index through HEC;
- REST search access to the `mcp_demo` index and the `mcp_service_demo` app;
- network access to HEC (commonly port 8088) and the management API (commonly port 8089).
