"""ROS-independent factory; Maria's statistical implementation is unchanged."""
import os
from did_agent.config import AgentConfig
from .energy import EnergyModel

def make_energy_model(config):
    return EnergyModel(config.energy_per_m, min_distance_m=config.energy_min_distance,
        max_energy_per_m=30.0, initial_energy_per_rad=None,
        min_angle_rad=config.energy_min_angle, max_energy_per_rad=30.0,
        max_turn_distance_m=config.turn_translation_tolerance,
        max_straight_angle_rad=config.straight_angle_tolerance)

def create_energy_model():
    path=os.environ.get('DID_AGENT_CONFIG')
    return make_energy_model(AgentConfig.load(path) if path else AgentConfig())
