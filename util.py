import numpy as np


def makeregressor(spike, p, intercept=True):
    """
    Construct spike regressor.
    :param spike: (T, N) spike trains
    :param p: order of regression
    :param intercept: indicator if intercept term included
    :return: (T, intercept + p * N) array
    """
    T, N = spike.shape
    regressor = np.ones((T, intercept + p * N), dtype=float)
    for t in range(T):
        if t - p >= 0:
            regressor[t, intercept:] = spike[t - p:t, :].flatten()  # by row
        else:
            regressor[t, intercept + (p - t) * N:] = spike[:t, :].flatten()
    return regressor


def inchol(n, w, tol):
    """
    Incomplete Cholesky decomposition for squared exponential covariance
    :param n: size of covariance matrix (n, n)
    :param w: inverse of squared lengthscale
    :param tol: stopping tolerance
    :return: (n, m) matrix
    """
    x = np.arange(n)
    diag = np.ones(n, dtype=float)
    pvec = np.arange(n, dtype=int)
    i = 0
    g = np.zeros((n, n), dtype=float)
    while diag[i:].sum() > tol:
        jast = np.argmax(diag[i:]) + i
        pvec[i], pvec[jast] = pvec[jast], pvec[i]
        g[jast, :i + 1][:], g[i, :i + 1][:] = g[i, :i + 1].copy(), g[jast, :i + 1].copy()
        g[i, i] = np.sqrt(diag[jast])
        g[i + 1:, i] = (np.exp(- w * np.square(x[pvec[i + 1:]] - x[pvec[i]]))
                        - np.dot(g[i + 1:, :i], g[i, :i].T)) / g[i, i]
        diag[i + 1:] = 1 - np.sum(np.square(g[i + 1:, :i + 1]), axis=1)

        i += 1
    return g[pvec, :i]


def sqexpcov(n, w, var=1.0):
    """
    Construct square exponential covariance matrix
    :param n: size
    :param w: inverse of squared lengthscale
    :param var: variance
    :return: (n, n) covariance matrix
    """
    i, j = np.meshgrid(np.arange(n), np.arange(n))
    return var * np.exp(-w * (i - j) ** 2)
