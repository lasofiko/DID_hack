from .navigation import distance, NavigationPlanner

class BatteryManager:
    def __init__(self, config):
        self.config = config
        self.rate = config.energy_per_m
        self.previous = None
        self.energy = None

    def observe(self, obs):
        if self.previous is not None:
            d = distance(obs['pose'],self.previous['pose'])
            used = self.previous['battery']-obs['battery']
            # Conservative upper estimate; short noisy measurements are ignored.
            if d >= 0.15 and used >= 0:
                self.rate = max(self.rate,used/d)
            if d < 0.15:
                return  # Keep anchor until accumulated displacement is measurable.
        self.previous = {'pose':dict(obs['pose']), 'battery':obs['battery']}

    def required(self, path):
        movement=NavigationPlanner.length(path)*self.rate
        turns=0.
        if self.energy:
            estimate,turns=self.energy.predict_components(path)
            movement=max(movement,estimate)
        return (movement+turns)*self.config.return_factor + self.config.battery_reserve

    def can_explore(self, battery, outgoing, home):
        return battery > self.required(outgoing+home)


class ReturnToBase:
    def __init__(self, planner, config):
        self.planner, self.config = planner, config

    def plan(self, pose):
        return self.planner.plan(pose,self.config.base)

    def arrived(self, pose):
        return distance(pose,self.config.base) <= self.config.base_tolerance
