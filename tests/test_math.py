from unittest import TestCase

import numpy as np
from scipy.linalg import toeplitz

from vlgp.math import ichol_gauss2, orth


class TestMath(TestCase):
    def test_ichol_gauss(self):
        np.random.seed(0)
        n = 500
        omega = 1
        dsq = np.arange(n) ** 2
        k = np.exp(- omega * dsq)
        K = toeplitz(k)
        G = ichol_gauss2(n, omega)
        self.assertTrue(np.allclose(K, G @ G.T))

    def test_orth(self):
        np.random.seed(0)
        n = 500
        p = 200
        q = 100
        x = np.random.randn(n, q)
        a = np.random.rand(q, p)
        x_orth, a_orth = orth(x, a)
        self.assertTrue(np.allclose(x @ a, x_orth @ a_orth))