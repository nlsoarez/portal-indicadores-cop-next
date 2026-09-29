from src.features.segments.common import GENERIC_OPERATIONAL_INDICATORS
from src.features.segments.empresarial import ENTERPRISE_INDICATORS
from src.features.segments.preventiva import PREVENTIVA_INDICATORS
from src.features.segments.residencial import RESIDENTIAL_INDICATORS


def _by_key(rows):
    return {row["indicator_key"]: row for row in rows}


def test_confirmed_indicator_targets():
    common = _by_key(GENERIC_OPERATIONAL_INDICATORS)
    residential = _by_key(RESIDENTIAL_INDICATORS)
    enterprise = _by_key(ENTERPRISE_INDICATORS)
    preventive = _by_key(PREVENTIVA_INDICATORS)

    assert common["dpa_official"]["target_value"] == 90.0
    assert common["dpa_official"]["direction"] == "higher_is_better"

    assert residential["res_etit_fibra_hfc"]["target_value"] == 90.0
    assert residential["res_etit_gpon"]["target_value"] == 90.0
    assert residential["res_assert_fibra_hfc"]["target_value"] == 85.0
    assert residential["res_assert_gpon"]["target_value"] == 85.0
    assert residential["chat_10m"]["target_value"] == 75.0
    assert residential["validacao_20m"]["target_value"] == 80.0
    assert residential["toa_cancellation_rate"]["target_value"] == 15.0
    assert residential["toa_cancellation_rate"]["direction"] == "lower_is_better"

    assert enterprise["emp_etit_event"]["target_value"] == 90.0
    assert enterprise["chat_10m"]["target_value"] == 75.0
    assert enterprise["validacao_20m"]["target_value"] == 80.0
    assert enterprise["toa_cancellation_rate"]["target_value"] == 15.0
    assert enterprise["toa_cancellation_rate"]["direction"] == "lower_is_better"
    assert enterprise["closing_assertiveness"]["target_value"] == 80.0

    assert preventive["chat_10m"]["target_value"] == 75.0
    assert preventive["validacao_20m"]["target_value"] == 80.0
    assert preventive["toa_cancellation_rate"]["target_value"] == 15.0
    assert preventive["toa_cancellation_rate"]["direction"] == "lower_is_better"
