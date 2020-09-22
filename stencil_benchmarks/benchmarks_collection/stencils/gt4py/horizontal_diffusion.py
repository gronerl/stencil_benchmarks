from stencil_benchmarks.benchmark import ParameterError
from stencil_benchmarks.benchmarks_collection.stencils import base

from gt4py import gtscript
from .mixin import StencilMixin


class Stencil(StencilMixin, base.HorizontalDiffusionStencil):
    @property
    def definition(self):
        def horizontal_diffusion(
            inp: gtscript.Field["dtype"],
            out: gtscript.Field["dtype"],
            coeff: gtscript.Field["dtype"],
        ):
            with computation(PARALLEL), interval(...):
                lap_field = 4.0 * inp[0, 0, 0] - (
                    inp[1, 0, 0]
                    + inp[-1, 0, 0]
                    + inp[0, 1, 0]
                    + inp[0, -1, 0]
                )
                res1 = lap_field[1, 0, 0] - lap_field[0, 0, 0]
                flx_field = (
                    0 if (res1 * (inp[1, 0, 0] - inp[0, 0, 0])) > 0 else res1
                )
                res2 = lap_field[0, 1, 0] - lap_field[0, 0, 0]
                fly_field = (
                    0 if (res2 * (inp[0, 1, 0] - inp[0, 0, 0])) > 0 else res2
                )
                out = inp[0, 0, 0] - coeff[0, 0, 0] * (
                    flx_field[0, 0, 0]
                    - flx_field[-1, 0, 0]
                    + fly_field[0, 0, 0]
                    - fly_field[0, -1, 0]
                )

        return horizontal_diffusion
