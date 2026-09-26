class GeometryState:
    def __init__(self, rad_prim: float, rad_sec: float, shift_in: float, shift_out: float, wrap_angle_prim: float, wrap_angle_sec: float, ratio: float):
        self.rad_prim = rad_prim
        self.rad_sec = rad_sec
        self.shift_in = shift_in
        self.shift_out = shift_out
        self.wrap_angle_prim = wrap_angle_prim
        self.wrap_angle_sec = wrap_angle_sec
        self.ratio = ratio