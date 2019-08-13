import abc
import os

import numpy as np

from .... import benchmark
from ....tools import cpphelpers, compilation, template

# pylint: disable=abstract-method,invalid-sequence-index,no-member


class StencilMixin(benchmark.Benchmark):
    compiler = benchmark.Parameter('compiler path', 'g++')
    compiler_flags = benchmark.Parameter(
        'compiler flags', '-xc++ -Ofast -fopenmp -Wall -march=native')
    print_code = benchmark.Parameter('print generated code', False)

    def setup(self):
        super().setup()
        code = self.generate_code()

        if self.print_code:
            print(cpphelpers.format_code(code))

        self.compiled = compilation.gnu_func(
            [self.compiler] + self.compiler_flags.split(), code, 'kernel')

    @property
    def ctype_name(self):
        return compilation.ctype_cname(compilation.dtype_as_ctype(self.dtype))

    @property
    def sorted_domain(self):
        # pylint: disable=invalid-unary-operand-type
        indices = np.argsort(-np.array(self.strides))
        return tuple(np.array(self.domain)[indices])

    @property
    def sorted_strides(self):
        return tuple(sorted(self.strides, key=lambda x: -x))

    @property
    def sorted_block_size(self):
        # pylint: disable=invalid-unary-operand-type
        indices = np.argsort(-np.array(self.strides))
        return tuple(np.array(self.block_size)[indices])

    @abc.abstractmethod
    def generate_code(self):
        pass

    def run_stencil(self, data):
        offset = (self.halo, ) * 3
        self.compiled(*(compilation.data_ptr(array, offset) for array in data))


class BasicStencilMixin(StencilMixin):
    loop = benchmark.Parameter('loop kind',
                               '1D',
                               choices=['1D', '3D', '3D-blocked'])
    block_size = benchmark.Parameter('block_size', (1, 1, 1))

    @abc.abstractmethod
    def stencil_body(self):
        pass

    def generate_code(self):
        template_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'basic_' + self.loop.lower().replace("-", "_") + '.template')
        return template.render(template_file,
                               args=self.args,
                               ctype=self.ctype_name,
                               strides=self.strides,
                               sorted_strides=self.sorted_strides,
                               domain=self.domain,
                               sorted_domain=self.sorted_domain,
                               block_size=self.block_size,
                               sorted_block_size=self.sorted_block_size,
                               body=self.stencil_body())


class VerticalAdvectionMixin(StencilMixin):
    loop = benchmark.Parameter('loop kind',
                               'k-innermost',
                               choices=['k-innermost', 'k-middle'])
    block_size = benchmark.Parameter('block_size', (1, 1))

    def generate_code(self):
        template_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'vertical_advection_' +
            self.loop.lower().replace("-", "_") + '.template')
        return template.render(template_file,
                               args=self.args,
                               ctype=self.ctype_name,
                               strides=self.strides,
                               domain=self.domain,
                               block_size=self.block_size)