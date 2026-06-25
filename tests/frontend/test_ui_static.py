#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path

import pytest


class UiParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self.groups = []
        self.ids = set()
        self._button = None
        self._group = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        classes = set(attributes.get("class", "").split())
        if tag == "button":
            self._button = {"tab": attributes.get("data-tab"), "text": ""}
        if "button-group-label" in classes:
            self._group = True

    def handle_data(self, data):
        if self._button is not None:
            self._button["text"] += data
        if self._group:
            self.groups.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "button" and self._button is not None:
            self._button["text"] = self._button["text"].strip()
            self.buttons.append(self._button)
            self._button = None
        if tag == "span":
            self._group = False


def _parse_static_ui() -> tuple[str, str, str, str, str, UiParser]:
    root = Path(__file__).resolve().parents[2]
    html = (root / "python-processor/static/index.html").read_text(encoding="utf-8")
    css = (root / "python-processor/static/app.css").read_text(encoding="utf-8")
    api_client = (root / "python-processor/static/api/api-client.js").read_text(encoding="utf-8")
    observation_format = (root / "python-processor/static/ui/observation-format.js").read_text(
        encoding="utf-8"
    )
    device_observation_view = (
        root / "python-processor/static/ui/device-observation-view.js"
    ).read_text(encoding="utf-8")
    spectrum_scale = (root / "python-processor/static/ui/spectrum-scale.js").read_text(
        encoding="utf-8"
    )
    parser = UiParser()
    parser.feed(html)
    return (
        html,
        css,
        api_client,
        observation_format,
        device_observation_view,
        spectrum_scale,
        parser,
    )


@pytest.mark.unit
def test_static_ui_contract() -> None:
    html, css, api_client, observation_format, device_observation_view, spectrum_scale, parser = (
        _parse_static_ui()
    )

    tabs = [button["text"] for button in parser.buttons if button["tab"]]
    assert tabs == [
        "Spektrum",
        "Wi-Fi",
        "Bluetooth / BLE",
        "RF Agent",
        "Felvételek",
        "ML osztályozás",
        "RAG",
        "Rendszerállapot",
    ]
    assert {
        "operationDialog",
        "operationForm",
        "operationFields",
        "operationSubmit",
        "operationCancel",
    } <= parser.ids
    assert {
        "startInput",
        "stopInput",
        "sdrangelAudioDevice",
        "sdrangelVolume",
        "sdrangelBrowserAudioStatus",
    } <= parser.ids
    assert {"spanReadout", "resolutionReadout", "markerReadout"} <= parser.ids
    assert (
        not {"centerInput", "spanInput", "btnWifi24", "btnWifi5", "btnGsm", "btnLte"} & parser.ids
    )
    assert (
        "export const FULL_MIN = 0" in spectrum_scale
        and "export const FULL_MAX = 24000" in spectrum_scale
    )
    assert "/ws/audio" in html and "prepareBrowserAudio" in html and "appendBrowserPcm" in html
    assert "synthetic_fallback_allowed" in html and "loadRuntimePolicy" in html
    assert "spectrumControlPanel" in html and "spectrumControlPanelToggle" in html
    assert "waterfallPanel" in html and "waterfallPanelToggle" in html
    assert "spectrumControlPanelCollapsed" in html and "waterfallPanelCollapsed" in html
    assert "maxhold-controller.js" in html
    assert "Vezérlőpanel elrejtése" in html and "Vízesés elrejtése" in html
    assert "Max Hold indítása" in html and "Csúcspont mentése" in html
    assert (
        "Ugrás csúcsra" not in html
        and "Csúcs mentése" not in html
        and "Overview / teljes tartomány" not in html
    )
    assert "prompt(" not in html and "confirm(" not in html
    assert html.index('<div class="panel waterfall-panel" id="waterfallPanel">') < html.index(
        '<div class="waterfall-control-strip">'
    )
    assert (
        "grid-template-rows:auto minmax(330px,42vh) auto auto auto auto auto minmax(92px,12vh)"
        in css
    )
    assert (
        "@media(max-height:760px)" in css
        and "grid-template-rows:auto 300px auto auto auto auto auto 90px" in css
    )
    assert (
        "@media(max-width:760px)" in css
        and "grid-template-rows:auto 320px auto auto auto auto auto 95px" in css
    )
    assert "height:clamp(360px, 40vh, 500px)" in css
    assert "margin-bottom:12px" in css
    assert ".canvas-wrap{position:relative;flex:1;min-height:0" in css
    assert "<th>Állapot</th>" in html
    assert "<th>Referencia</th>" in html
    assert "<th>Utolsó észlelés / age</th>" in html
    assert "<th>AP/kliens típus</th>" in html
    assert "<th>Titkosítás</th>" in html
    assert "<th>Mgmt / riasztás</th>" in html
    assert "<th>Kockázat</th>" in html
    assert (
        '<tbody id="wifiObservationRows"><tr><td colspan="12">Nincs Wi-Fi adat.</td></tr></tbody>'
        in html
    )
    assert "<th>Feltételezett keretküldő</th>" in html
    assert (
        '<tbody id="wifiSecurityEventRows"><tr><td colspan="10">Nincs Wi-Fi security '
        "esemény.</td></tr></tbody>" in html
    )
    assert "Kismet alert import" in html
    assert "<th>Vendor mód</th>" in html
    assert "<th>Service / profile</th>" in html
    assert (
        '<tbody id="bluetoothObservationRows"><tr><td colspan="11">Nincs Bluetooth '
        "adat.</td></tr></tbody>" in html
    )
    assert "item.source_name || item.source_type" not in html
    assert "/api/wifi/devices" in api_client
    assert "/api/wifi/security-events" in api_client
    assert "/api/import/kismet/alerts" in api_client
    assert "/api/bluetooth/devices" in api_client
    assert "/api/wifi/observations?measurement_session_id" not in html
    assert "/api/bluetooth/observations?measurement_session_id" not in html
    assert "formatRssiSummary" in observation_format
    assert "previous_signal_dbm" in device_observation_view
    assert "previous_rssi_dbm" in device_observation_view
    assert "formatAge" in observation_format
    assert "formatExactTime" in observation_format
    assert (
        "formatPresenceState" not in html
        and "formatPresenceState" not in observation_format
        and "formatPresenceState" not in device_observation_view
    )
    assert "formatRiskSummary" in observation_format
    assert "formatManagementSummary" in observation_format
    assert "formatServiceSummary" in observation_format
    assert "renderWifiSecurityEvents" in html
    assert "importKismetAlerts" in html

    assert "<th>Jelenlét</th>" not in html
    assert "BASELINE_STATUS_LABELS" not in html
    assert "'transient'" not in html and '"transient"' not in html
    assert "Nincs aktív vagy kiválasztott mérési session." in html
    assert "Új session indítása" in html and "Korábbi session megnyitása" in html
    assert {
        "wifiSessionEmptyState",
        "wifiSessionContent",
        "bluetoothSessionEmptyState",
        "bluetoothSessionContent",
    } <= parser.ids
    assert {
        "referenceBar",
        "referenceBarLabel",
        "referenceBarSpectrum",
        "referenceBarWifi",
        "referenceBarBluetooth",
    } <= parser.ids
    assert {"btnReferenceBarLoad", "btnReferenceBarRemove", "btnReferenceBarDetails"} <= parser.ids
    assert {"detailDialog", "detailDialogTitle", "detailDialogBody"} <= parser.ids
    assert "let viewedSession" in html
    assert "function setViewedSession" in html
    assert "reference_set_id" in html
    assert "require_session" in html
    assert "export function formatReferenceStatus" in observation_format
    assert "function renderReferenceSummary" in html
    assert "function showMissingReferenceDevices" in html
    assert "function openDeviceReferenceDetails" in html

    wifi_section = html[html.index('id="wifiTab"') : html.index('id="bluetoothTab"')]
    bluetooth_section = html[html.index('id="bluetoothTab"') : html.index('id="rfAgentTab"')]
    assert "<th>Forrás</th>" not in wifi_section
    assert "<th>Forrás</th>" not in bluetooth_section
    for label in [
        "Pillanatkép rögzítése",
        "Max Hold rögzítése referenciának",
        "Referencia mentése",
        "Betöltés",
        "Referencia export",
        "Referencia törlése",
        "DB referencia-réteg",
    ]:
        assert any(button["text"] == label for button in parser.buttons), label
