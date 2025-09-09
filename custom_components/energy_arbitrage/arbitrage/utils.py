import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Union, Dict, List
import zoneinfo

# Global HA reference for centralized timezone access
_global_hass = None
_ha_timezone_cache = None

_LOGGER = logging.getLogger(__name__)

def set_global_hass(hass):
    """Set global HA reference during integration setup."""
    global _global_hass, _ha_timezone_cache
    _global_hass = hass
    # Reset cache when HA reference changes
    _ha_timezone_cache = None
    if hass and hasattr(hass.config, 'time_zone'):
        _LOGGER.debug(f"Global HA timezone initialized: {hass.config.time_zone}")
    else:
        raise RuntimeError("HA reference provided but no timezone configuration found")


def clear_global_hass():
    """Clear global HA reference during integration cleanup."""
    global _global_hass, _ha_timezone_cache
    _global_hass = None
    _ha_timezone_cache = None
    _LOGGER.debug("Global HA reference cleared")


def get_ha_timezone() -> timezone:
    """Get Home Assistant configured timezone - no parameters needed.
    
    Raises:
        RuntimeError: If global HA reference not set or timezone config missing
    """
    global _global_hass, _ha_timezone_cache
    
    if _global_hass is None:
        raise RuntimeError("Global HA reference not set - call set_global_hass() during integration setup")
    
    if not hasattr(_global_hass.config, 'time_zone'):
        raise RuntimeError("Home Assistant timezone configuration missing")
    
    try:
        # Cache the timezone to avoid repeated zoneinfo calls
        if _ha_timezone_cache is None:
            _ha_timezone_cache = zoneinfo.ZoneInfo(_global_hass.config.time_zone)
            _LOGGER.debug(f"Cached HA timezone: {_global_hass.config.time_zone}")
        return _ha_timezone_cache
    except Exception as e:
        raise RuntimeError(f"Failed to create timezone from '{_global_hass.config.time_zone}': {e}") from e

def safe_float(state, default: float = 0.0) -> float:
    if not state:
        return default
    
    try:
        if hasattr(state, 'state'):
            value = state.state
        else:
            value = state
            
        if value in ['unknown', 'unavailable', '', None]:
            return default
            
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(state, default: int = 0) -> int:
    if not state:
        return default
    
    try:
        if hasattr(state, 'state'):
            value = state.state
        else:
            value = state
            
        if value in ['unknown', 'unavailable', '', None]:
            return default
            
        return int(float(value))
    except (ValueError, TypeError):
        return default

def parse_datetime(dt_string: str) -> Optional[datetime]:
    """Parse datetime string with proper timezone handling - no parameters needed.
    
    Args:
        dt_string: ISO datetime string to parse
        
    Returns:
        datetime: Parsed datetime in HA timezone, or None if parsing fails
        
    Raises:
        RuntimeError: If global HA reference not set
    """
    try:
        if not dt_string:
            return None
        
        ha_tz = get_ha_timezone()
            
        # Handle UTC 'Z' suffix
        if dt_string.endswith('Z'):
            # Parse as UTC, then convert to HA timezone
            utc_dt = datetime.fromisoformat(dt_string[:-1]).replace(tzinfo=timezone.utc)
            return utc_dt.astimezone(ha_tz)
        
        # Handle explicit timezone offset (like +00:00)
        if '+' in dt_string or dt_string.count('-') >= 3:  # ISO format with timezone
            parsed_dt = datetime.fromisoformat(dt_string)
            return parsed_dt.astimezone(ha_tz)
        
        # Assume UTC if no timezone info, then convert to HA timezone
        utc_dt = datetime.fromisoformat(dt_string).replace(tzinfo=timezone.utc)
        return utc_dt.astimezone(ha_tz)
        
    except (ValueError, TypeError) as e:
        _LOGGER.warning(f"Failed to parse datetime '{dt_string}': {e}")
        return None

def calculate_battery_capacity_wh(level_percent: float, total_capacity_wh: float) -> float:
    return (level_percent / 100.0) * total_capacity_wh

def calculate_available_battery_capacity(
    current_level_percent: float, 
    min_reserve_percent: float, 
    total_capacity_wh: float
) -> float:
    available_percent = max(0, current_level_percent - min_reserve_percent)
    return (available_percent / 100.0) * total_capacity_wh

def calculate_battery_charge_time(
    target_level_percent: float,
    current_level_percent: float, 
    total_capacity_wh: float,
    charge_power_w: float
) -> float:
    if charge_power_w <= 0:
        return float('inf')
    
    needed_percent = target_level_percent - current_level_percent
    if needed_percent <= 0:
        return 0.0
    
    needed_wh = (needed_percent / 100.0) * total_capacity_wh
    return needed_wh / charge_power_w

def get_current_price_data(price_data: List[Dict], current_time: datetime = None) -> Optional[Dict]:
    """Get current price data entry matching current HA timezone time."""
    if not price_data:
        return None
    
    if current_time is None:
        ha_tz = get_ha_timezone()
        current_time = datetime.now(ha_tz)
    
    for entry in price_data:
        start_time = parse_datetime(entry.get('start', ''))
        end_time = parse_datetime(entry.get('end', ''))
        
        if start_time and end_time and start_time <= current_time < end_time:
            return entry
    
    return None


def calculate_battery_degradation_cost(
    energy_amount_wh: float,
    battery_capacity_wh: float,
    battery_cost: float,
    rated_cycles: int,
    degradation_factor: float = 1.0
) -> Dict[str, float]:
    depth_of_discharge = min(energy_amount_wh / battery_capacity_wh, 1.0)
    
    equivalent_cycles = depth_of_discharge * degradation_factor
    
    cost_per_cycle = battery_cost / rated_cycles
    
    degradation_cost = equivalent_cycles * cost_per_cycle
    
    return {
        'degradation_cost': degradation_cost,
        'equivalent_cycles': equivalent_cycles,
        'cost_per_cycle': cost_per_cycle,
        'depth_of_discharge': depth_of_discharge
    }

def calculate_arbitrage_profit(
    buy_price: float,
    sell_price: float, 
    energy_amount_wh: float,
    battery_efficiency: float = 0.9,
    battery_specs: Optional[Dict[str, float]] = None,
    include_degradation: bool = False
) -> Dict[str, float]:
    # Convert Wh to kWh for price calculations (prices are per kWh)
    energy_amount_kwh = energy_amount_wh / 1000.0
    gross_profit = (sell_price - buy_price) * energy_amount_kwh
    efficiency_loss_kwh = energy_amount_kwh * (1 - battery_efficiency)
    efficiency_cost = efficiency_loss_kwh * buy_price
    
    degradation_cost = 0.0
    degradation_info = {}
    
    if include_degradation and battery_specs:
        degradation_info = calculate_battery_degradation_cost(
            energy_amount_wh,
            battery_specs.get('capacity', 15000),  # Default capacity in Wh
            battery_specs.get('cost', 7500),
            battery_specs.get('cycles', 6000),
            battery_specs.get('degradation_factor', 1.0)
        )
        degradation_cost = degradation_info['degradation_cost']
    
    net_profit = gross_profit - efficiency_cost - degradation_cost
    roi_percent = (net_profit / (buy_price * energy_amount_kwh)) * 100 if buy_price > 0 else 0
    
    result = {
        'gross_profit': gross_profit,
        'efficiency_cost': efficiency_cost,
        'degradation_cost': degradation_cost,
        'net_profit': net_profit,
        'roi_percent': roi_percent
    }
    
    if degradation_info:
        result.update({
            'equivalent_cycles': degradation_info['equivalent_cycles'],
            'depth_of_discharge': degradation_info['depth_of_discharge'],
            'cost_per_cycle': degradation_info['cost_per_cycle']
        })
    
    return result


def get_current_ha_time() -> datetime:
    """Get current time in Home Assistant timezone - no parameters needed.
    
    Raises:
        RuntimeError: If global HA reference not set
    """
    ha_tz = get_ha_timezone()
    return datetime.now(ha_tz)


def convert_utc_to_ha_time(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to Home Assistant timezone - no parameters needed.
    
    Args:
        utc_dt: UTC datetime to convert
        
    Returns:
        datetime: Converted to HA timezone
        
    Raises:
        RuntimeError: If global HA reference not set
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    
    ha_tz = get_ha_timezone()
    return utc_dt.astimezone(ha_tz)


def format_ha_time(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Format datetime with timezone info for logging/display."""
    return dt.strftime(format_str)


def validate_config(config: Dict[str, Any]) -> List[str]:
    errors = []
    
    required_sensors = [
        'pv_power_sensor',
        'battery_level_sensor',
        'battery_power_sensor',
        'load_power_sensor',
        'grid_power_sensor'
    ]
    
    for sensor in required_sensors:
        if not config.get(sensor):
            errors.append(f"Missing required sensor: {sensor}")
    
    if config.get('battery_capacity', 0) <= 0:
        errors.append("Battery capacity must be greater than 0")
    
    if config.get('max_pv_power', 0) <= 0:
        errors.append("Max PV power must be greater than 0")
    
    min_reserve = config.get('min_battery_reserve', 0)
    if not 0 <= min_reserve <= 100:
        errors.append("Min battery reserve must be between 0-100%")
    
    efficiency = config.get('battery_efficiency', 90)
    if not 0 <= efficiency <= 100:
        errors.append("Battery efficiency must be between 0-100%")
    
    return errors