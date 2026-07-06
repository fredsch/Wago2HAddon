"""Constants for the Wago2HAddon integration."""
from __future__ import annotations

DOMAIN = "wago2haddon"

# --- Config entry keys -------------------------------------------------------
CONF_HOST = "host"
CONF_MODBUS_PORT = "modbus_port"
CONF_UDP_PORT = "udp_port"
CONF_LOCAL_IP = "local_ip"
CONF_HEARTBEAT_INTERVAL = "heartbeat_interval"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_WAGO_841 = "wago_841"
CONF_XML_PATH = "calaos_xml_path"
CONF_MULTI_CLICK_MS = "multi_click_ms"
CONF_LONG_PRESS_MS = "long_press_ms"

# --- Defaults ----------------------------------------------------------------
DEFAULT_MODBUS_PORT = 502
DEFAULT_UDP_PORT = 4646  # WAGO_LISTEN_PORT in calaos_base (src/lib/Utils.h)
DEFAULT_HEARTBEAT_INTERVAL = 10.0  # seconds; PLC standalone timeout is 30 s
DEFAULT_SCAN_INTERVAL = 120  # seconds; analog/temperature polling (user requirement)
DEFAULT_WAGO_841 = True  # 750-8xx family (750-881 included)
DEFAULT_MULTI_CLICK_MS = 350
DEFAULT_LONG_PRESS_MS = 500

# --- Modbus address offsets (must match calaos_base exactly) -----------------
# src/lib/Utils.h
WAGO_841_START_ADDRESS = 4096  # added to output coil address when writing
WAGO_KNX_START_ADDRESS = 6144
# WagoExternProc_main.cpp: read_output_bits/read_output_words add this offset
OUTPUT_READBACK_OFFSET = 0x200  # 512

MODBUS_SLAVE_ID = 1

# --- UDP protocol strings ----------------------------------------------------
CMD_HEARTBEAT = "WAGO_HEARTBEAT"
CMD_SET_SERVER_IP = "WAGO_SET_SERVER_IP"
CMD_DALI_SET = "WAGO_DALI_SET"
CMD_DALI_GET = "WAGO_DALI_GET"
MSG_INPUT_PREFIX = "WAGO INT"
MSG_KNX_PREFIX = "WAGO KNX"

# --- Platforms ---------------------------------------------------------------
PLATFORMS = ["light", "switch", "cover", "sensor", "binary_sensor", "event"]

# --- Calaos IO type names ----------------------------------------------------
T_INPUT_BP = "WIDigitalBP"
T_INPUT_TRIPLE = "WIDigitalTriple"
T_INPUT_LONG = "WIDigitalLong"
T_OUTPUT_DIGITAL = "WODigital"
T_OUTPUT_DALI = "WODali"
T_OUTPUT_DALI_RGB = "WODaliRVB"
T_OUTPUT_VOLET = "WOVolet"
T_OUTPUT_VOLET_SMART = "WOVoletSmart"
T_INPUT_TEMP = "WITemp"
T_INPUT_ANALOG = "WIAnalog"

WAGO_TYPES = {
    T_INPUT_BP,
    T_INPUT_TRIPLE,
    T_INPUT_LONG,
    T_OUTPUT_DIGITAL,
    T_OUTPUT_DALI,
    T_OUTPUT_DALI_RGB,
    T_OUTPUT_VOLET,
    T_OUTPUT_VOLET_SMART,
    T_INPUT_TEMP,
    T_INPUT_ANALOG,
}

# --- Event types emitted by input entities -----------------------------------
EV_SINGLE = "single_click"
EV_DOUBLE = "double_click"
EV_TRIPLE = "triple_click"
EV_LONG = "long_press"
EV_PRESS = "press"
EV_RELEASE = "release"
