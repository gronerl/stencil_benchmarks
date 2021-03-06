import contextlib
import itertools

import dace
from gt4py.testing.utils import build_dace_adhoc
from gt4py.testing.utils import ApplyOTFOptimizer,DeduplicateAccesses, PrefetchingKCaches, PruneTransientOutputs, SubgraphFusion
from stencil_benchmarks.benchmark import Parameter, Benchmark


class GT4PyStencilMixin(Benchmark):

    use_prune_transient_outputs = Parameter("Switch pruning of transient output accesses on or off", default=True)
    use_deduplicate_accesses = Parameter("Only access each offset once per map and field.", default=False)
    use_otf_transform = Parameter("use_otf_transform", default=True)
    use_subgraph_fusion = Parameter("use_subgraph_fusion", default=True)
    use_prefetching = Parameter("use_prefetching", default=False)
    prefetch_arrays = Parameter("prefetch_arryas", default="", dtype=str, nargs=1)
    loop_order = Parameter(
        "loop_order",
        default="IJK",
        choices=list("".join(p) for p in itertools.permutations("IJK")),
    )

    def setup(self):
        super().setup()
        halo = (self.halo,) * 3
        alignment = max(self.parameters["alignment"], 1)
        passes = []
        if self.parameters["use_prune_transient_outputs"]:
            passes.append(PruneTransientOutputs())
        if self.parameters["use_otf_transform"]:
            passes.append(ApplyOTFOptimizer())
        if self.parameters["use_subgraph_fusion"]:
            passes.append(SubgraphFusion(storage_type=dace.dtypes.StorageType.Register))
        if self.parameters['use_deduplicate_accesses']:
            passes.append(DeduplicateAccesses())
        if self.parameters["use_prefetching"]:
            arrays = self.parameters["prefetch_arrays"].split(",")
            passes.append(PrefetchingKCaches(arrays=arrays))

        kwargs = {}
        if "backend" in self.parameters:
            kwargs["backend"] = self.parameters["backend"]
        if "gpu_block_size" in self.parameters:
            kwargs["gpu_block_size"] = ",".join(
                str(b) for b in self.parameters["gpu_block_size"]
            )
        if hasattr(self, "constants"):
            kwargs["constants"] = self.constants
        self._gt4py_stencil_object = build_dace_adhoc(
            definition=self.definition,
            domain=self.domain,
            halo=halo,
            specialize_strides=self.strides,
            dtype=self.parameters["dtype"],
            passes=passes,
            alignment=alignment,
            layout=self.parameters["layout"],
            loop_order=self.parameters["loop_order"],
            device=self.device,
            **kwargs
        )


class GPUStencilMixin(GT4PyStencilMixin):
    device = "gpu"

    backend = Parameter("backend", choices=["cuda", "hip"], default="cuda")
    gpu_block_size = Parameter("GPU thread block size", default=(64, 2, 1))

    @contextlib.contextmanager
    def on_device(self, data):
        from ..cuda_hip import api
        from stencil_benchmarks.tools import array

        runtime = api.runtime(self.backend)

        device_data = [
            array.alloc_array(
                self.domain_with_halo,
                self.dtype,
                self.layout,
                self.alignment,
                index_to_align=(self.halo,) * 3,
                alloc=runtime.malloc,
                apply_offset=self.offset_allocations,
            )
            for _ in data
        ]

        for host_array, device_array in zip(data, device_data):
            runtime.memcpy(
                device_array.ctypes.data,
                host_array.ctypes.data,
                array.nbytes(host_array),
                "HostToDevice",
            )
        runtime.device_synchronize()
        from types import SimpleNamespace

        device_data_wrapped = [
            SimpleNamespace(__cuda_array_interface__=o.__array_interface__)
            for o in device_data
        ]

        yield device_data_wrapped

        for host_array, device_array in zip(data, device_data):
            runtime.memcpy(
                host_array.ctypes.data,
                device_array.ctypes.data,
                array.nbytes(host_array),
                "DeviceToHost",
            )
        runtime.device_synchronize()


class CPUStencilMixin(GT4PyStencilMixin):
    device = "cpu"

    @contextlib.contextmanager
    def on_device(self, data):
        yield data
