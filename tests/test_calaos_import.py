"""Parsing of a Calaos io.xml into Wago IO models."""
from conftest import load

imp = load("calaos_import")
models = load("models")

IO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<calaos:ioconfig xmlns:calaos="http://www.calaos.fr">
  <calaos:home>
    <calaos:room name="Salon" type="salon">
      <calaos:input type="WIDigitalBP" id="input_1" name="BP porte" host="10.0.0.5" var="3"/>
      <calaos:input type="WIDigitalTriple" id="input_2" name="BP triple" host="10.0.0.5" var="4"/>
      <calaos:input type="WIDigitalLong" id="input_3" name="BP long" host="10.0.0.5" var="5"/>
      <calaos:output type="WODigital" id="output_1" name="Plafonnier" host="10.0.0.5" var="0" gui_type="light"/>
      <calaos:output type="WODigital" id="output_2" name="Pompe" host="10.0.0.5" var="1" gui_type="light" io_style="pump"/>
      <calaos:output type="WODigital" id="output_3" name="Prise" host="10.0.0.5" var="2" gui_type="light" io_style="outlet" wago_841="false"/>
      <calaos:output type="WODigital" id="output_4" name="KNX" host="10.0.0.5" var="7" knx="true"/>
      <calaos:output type="WOVoletSmart" id="output_5" name="Volet" host="10.0.0.5" var_up="8" var_down="9" time_up="25" time_down="22"/>
      <calaos:output type="WODali" id="output_6" name="Spot" host="10.0.0.5" line="1" address="12" group="0" fade_time="2"/>
      <calaos:output type="WODaliRVB" id="output_7" name="Ruban" host="10.0.0.5" rline="1" raddress="100" gaddress="101" baddress="102"/>
      <calaos:input type="WITemp" id="input_4" name="Temp" host="10.0.0.5" var="20" offset="-0.5"/>
      <calaos:output type="WODigital" id="output_8" name="Desactive" host="10.0.0.5" var="10" enabled="false"/>
      <calaos:output type="WODigital" id="output_9" name="Autre PLC" host="10.0.0.6" var="0"/>
      <calaos:internal type="InternalBool" id="intern_1" name="Interne"/>
    </calaos:room>
  </calaos:home>
</calaos:ioconfig>
"""


def parse(tmp_path, only_host="10.0.0.5"):
    path = tmp_path / "io.xml"
    path.write_text(IO_XML, encoding="utf-8")
    return {d.io_id: d for d in imp.parse_calaos_xml(str(path), only_host)}


def test_host_filter_and_disabled(tmp_path):
    devs = parse(tmp_path)
    assert "output_9" not in devs  # other PLC
    assert "output_8" not in devs  # enabled="false"
    assert "intern_1" not in devs  # not a Wago IO
    assert len(parse(tmp_path, only_host=None)) == len(devs) + 1


def test_inputs(tmp_path):
    devs = parse(tmp_path)
    assert [devs[i].kind for i in ("input_1", "input_2", "input_3")] == ["bp", "triple", "long"]
    assert devs["input_1"].var == 3
    assert devs["input_1"].room == "Salon"


def test_digital_outputs_and_io_style(tmp_path):
    devs = parse(tmp_path)
    assert devs["output_1"].as_light is True
    assert devs["output_2"].as_light is False and devs["output_2"].style == "pump"
    assert devs["output_3"].as_light is False and devs["output_3"].wago_841 is False
    assert devs["output_4"].knx is True


def test_shutter_dali_temp(tmp_path):
    devs = parse(tmp_path)
    shutter = devs["output_5"]
    assert isinstance(shutter, models.ShutterOutput)
    assert (shutter.var_up, shutter.var_down, shutter.time_up, shutter.time_down) == (8, 9, 25.0, 22.0)
    dali = devs["output_6"]
    assert (dali.channel.address, dali.channel.fade_time) == (12, 2)
    rgb = devs["output_7"]
    assert (rgb.red.address, rgb.green.address, rgb.blue.address) == (100, 101, 102)
    temp = devs["input_4"]
    assert temp.is_temp and temp.var == 20 and temp.offset == -0.5
