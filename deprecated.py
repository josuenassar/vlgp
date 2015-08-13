def variational2(y, mu, sigma, p, omega=None,
                 a0=None, b0=None, m0=None, V0=None, K0=None,
                 r0=np.finfo(float).eps, maxiter=5, inneriter=5, tol=np.finfo(float).eps,
                 verbose=False):
    """
    :param y: (T, N), spike trains
    :param mu: (T, L), prior mean
    :param sigma: (L, T, T), prior covariance
    :param omega: (L, T, T), inverse prior covariance
    :param p: order of autoregression
    :param maxiter: maximum number of iterations
    :param tol: convergence tolerance
    :return
        m: posterior mean
        V: posterior covariance
        b: coefficients of y
        a: coefficients of x
        lbound: lower bound sequence
        it: number of iterations
    """

    def updaterate(t, n):
        # rate = E(E(y|x))
        for t, n in itertools.product(t, n):
            rate[t, n] = saferate(t, n, Y, m, V, b, a)

    start = time.time()  # time when algorithm starts

    # dimensions
    T, N = y.shape
    _, L = mu.shape

    # identity matrix
    id_m = np.identity(T)
    id_a = np.identity(L)
    id_b = np.identity(1 + p * N)
    id_coef = np.identity(1 + p * N + L)

    # calculate inverse of prior covariance if not given
    if omega is None:
        omega = np.empty_like(sigma)
        for l in range(L):
            omega[l, :, :] = np.linalg.inv(sigma[l, :, :])

    # read-only variables, protection from unexpected assignment
    y.setflags(write=0)
    mu.setflags(write=0)
    sigma.setflags(write=0)
    omega.setflags(write=0)

    # initialize args
    # make a copy to avoid changing initial values
    if m0 is None:
        m = mu.copy()
    else:
        m = m0.copy()

    if V0 is None:
        V = sigma.copy()
    else:
        V = V0.copy()

    if K0 is None:
        K = omega.copy()
    else:
        K = np.empty_like(V)
        for l in range(L):
            K[l, :, :] = np.linalg.inv(V[l, :, :])

    if a0 is None:
        a = np.zeros((L, N))
    else:
        a = a0.copy()

    if b0 is None:
        b = np.zeros((1 + p * N, N))
    else:
        b = b0.copy()

    coef = np.empty((1 + p*N + L, N))
    coef[:1 + p * N, :] = b
    coef[1 + p * N:, :] = a

    # construct history
    Y = np.zeros((T, 1 + p * N), dtype=float)
    Y[:, 0] = 1
    for t in range(T):
        if t - p >= 0:
            Y[t, 1:] = y[t - p:t, :].flatten()  # vectorized by row
        else:
            Y[t, 1 + (p - t) * N:] = y[:t, :].flatten()

    # initialize rate matrix
    # rate = E(E(y|x))
    rate = np.empty_like(y)
    updaterate(range(T), range(N))

    # initialize lower bound
    lbound = np.full(maxiter, np.NINF, dtype=float)
    lbound[0] = lowerbound(y, Y, mu, omega, m, V, b, a)

    # old values
    old_coef = coef.copy()
    old_m = m.copy()
    old_V = V.copy()

    it = 1
    convergent = False
    # MIN_DELTA = tol * (a.size + b.size + m.size + V.size)
    while not convergent and it < maxiter:
        # optimize coefficients
        for n in range(N):
            # optimize b[:, n]
            for _ in range(inneriter):
                grad_coef = np.zeros(1 + p * N + L)
                hess_coef = np.zeros((1 + p * N + L, 1 + p * N + L))
                for t in range(T):
                    grad_coef[:1 + p * N] = np.nan_to_num(grad_coef[:1 + p * N] + (y[t, n] - rate[t, n]) * Y[t, :])
                    hess_coef[:1 + p * N, :1 + p * N] = np.nan_to_num(hess_coef[:1 + p * N, :1 + p * N] - rate[t, n] * np.outer(Y[t, :], Y[t, :]))
                    w = m[t, :] + V[:, t, t] * coef[1 + p * N:, n]
                    grad_coef[1 + p * N:] = grad_coef[1 + p * N:] + y[t, n] * m[t, :] - rate[t, n] * w
                    hess_coef[1 + p * N:, 1 + p * N:] = hess_coef[1 + p * N:, 1 + p * N:] - rate[t, n] * (np.outer(w, w) + np.diag(V[:, t, t]))
                    hess_coef[:1 + p * N, 1 + p * N:] = hess_coef[:1 + p * N, 1 + p * N:] - rate[t, n] * np.outer(Y[t, :], w)
                    hess_coef[1 + p * N, :1 + p * N] = hess_coef[:1 + p * N, 1 + p * N:].T
                r = r0
                hess_ = hess_coef - r * id_coef
                coef[:, n] = coef[:, n] - np.linalg.solve(hess_, grad_coef)
                coef[1 + p*N:, n] = coef[1 + p*N:, n] / np.linalg.norm(coef[1 + p*N:, n])
                updaterate(range(T), [n])

            # roll back
            lb = lowerbound(y, Y, mu, omega, m, V, coef[:1 + p*N, :], coef[1 + p*N:, :])
            if np.isnan(lb) or lb < lbound[it - 1]:
                if verbose:
                    print 'alpha rolled back, lb = %.5f' % lb
                coef[1 + p*N:, n] = old_coef[1 + p*N:, n]
                updaterate(range(T), [n])

        # optimize posterior
        for l in range(L):
            # optimize V[l]
            for t in range(T):
                k_ = K[l, t, t] - 1 / V[l, t, t]  # \tilde{k}_tt
                old_vtt = V[l, t, t]
                # fixed point iterations
                for _ in range(inneriter):
                    V[l, t, t] = 1 / (omega[l, t, t] - k_ + np.dot(rate[t, :], coef[1 + p*N+ l, :] * coef[1 + p*N+ l, :]))
                    updaterate([t], range(N))
                # update V
                not_t = np.arange(T) != t
                V[np.ix_([l], not_t, not_t)] = V[np.ix_([l], not_t, not_t)] \
                                               + (V[l, t, t] - old_vtt) \
                                                 * np.outer(V[l, t, not_t], V[l, t, not_t]) / (old_vtt * old_vtt)
                V[l, t, not_t] = V[l, not_t, t] = V[l, t, t] * V[l, t, not_t] / old_vtt
                # update k_tt
                K[l, t, t] = k_ + 1 / V[l, t, t]
            updaterate(range(T), range(N))
            # roll back
            lb = lowerbound(y, Y, mu, omega, m, V, coef[:1 + p*N, :], coef[1 + p*N:, :])
            if np.isnan(lb) or lb < lbound[it - 1]:
                if verbose:
                    print 'V rolled back, lb = %.5f' % lb
                V[l, :, :] = old_V[l, :, :]
                updaterate(range(T), range(N))

            # optimize m[l]
            for _ in range(inneriter):
                grad_m = np.nan_to_num(np.dot(y - rate, a[l, :]) - np.dot(omega[l, :, :], (m[:, l] - mu[:, l])))
                hess_m = np.nan_to_num(-np.diag(np.dot(rate, a[l, :] * a[l, :]))) - omega[l, :, :]
                r = r0
                hess_ = hess_m - r * id_m
                m[:, l] = m[:, l] - np.linalg.solve(hess_, grad_m)
                updaterate(range(T), range(N))
            # roll back if lower bound decreased
            lb = lowerbound(y, Y, mu, omega, m, V, coef[:1 + p*N, :], coef[1 + p*N:, :])
            if np.isnan(lb) or lb < lbound[it - 1]:
                if verbose:
                    print 'm rolled back, lb = %.5f' % lb
                m[:, l] = old_m[:, l]
                updaterate(range(T), range(N))

        # update lower bound
        lbound[it] = lowerbound(y, Y, mu, omega, m, V, coef[:1 + p*N, :], coef[1 + p*N:, :])

        # check convergence
        delta = np.linalg.norm(old_coef - coef) + np.linalg.norm(old_m - m) + np.linalg.norm(old_V - V)

        if delta < tol:
            convergent = True

        if verbose:
            print 'Iteration[%d]:' % (it + 1), 'L = %.5f' % lbound[it], 'delta = %.5f' % delta

        old_coef[:] = coef
        old_m[:] = m
        old_V[:] = V

        it += 1

    if it == maxiter:
        warnings.warn('not convergent', RuntimeWarning)

    stop = time.time()

    return m, V, coef[:1 + p*N, :], coef[1 + p*N:, :], lbound, it, stop - start


# bias term
def variational2(y, mu, sigma, p, omega=None,
                 a0=None, b0=None, m0=None, V0=None, K0=None, bias0=None,
                 maxiter=5, inneriter=5, tol=1e-6,
                 verbose=False):
    """
    :param y: (T, N), spike trains
    :param mu: (T, L), prior mean
    :param sigma: (L, T, T), prior covariance
    :param omega: (L, T, T), inverse prior covariance
    :param p: order of history
    :param maxiter: maximum number of iterations
    :param tol: convergence tolerance
    :return
        m: posterior mean
        V: posterior covariance
        b: coefficients of y
        a: coefficients of x
        lbound: lower bound sequence
        it: number of iterations
    """

    def lowerbound():
        lb = np.sum(y * (np.dot(Y, b) + np.dot(m + bias, a)) - rate)

        for l in range(L):
            lb += -0.5 * np.dot(m[:, l] - mu[:, l], np.dot(omega[l, :, :], m[:, l] - mu[:, l])) + \
                  -0.5 * np.trace(np.dot(omega[l, :, :], V[l, :, :])) + 0.5 * np.linalg.slogdet(V[l, :, :])[1]
        return lb

    def updaterate(t, n):
        # rate = E(E(y|x))
        for t, n in itertools.product(t, n):
            lograte = np.inner(Y[t, :], b[:, n]) + np.inner(m[t, :] + bias, a[:, n]) \
                      + 0.5 * np.sum(a[:, n] * a[:, n] * V[:, t, t])
            rate[t, n] = np.nan_to_num(np.exp(lograte)) if np.exp(lograte) > 0 else eps

    start = time.time()  # time when algorithm starts

    # epsilon
    eps = np.finfo(np.float).eps

    # dimensions
    T, N = y.shape
    _, L = mu.shape

    # identity matrix
    hess_adj_b = eps * np.identity(p * N)

    # calculate inverse of prior covariance if not given
    if omega is None:
        omega = np.empty_like(sigma)
        for l in range(L):
            omega[l, :, :] = np.linalg.inv(sigma[l, :, :])

    # read-only variables, protection from unexpected assignment
    y.setflags(write=0)
    mu.setflags(write=0)
    sigma.setflags(write=0)
    omega.setflags(write=0)

    # construct history
    Y = history(y, p, False)

    # initialize args
    # make a copy to avoid changing initial values
    if m0 is None:
        m = mu.copy()
    else:
        m = m0.copy()

    if V0 is None:
        V = sigma.copy()
    else:
        V = V0.copy()

    if K0 is None:
        K = omega.copy()
    else:
        K = np.empty_like(V)
        for l in range(L):
            K[l, :, :] = np.linalg.inv(V[l, :, :])

    Y_ = np.concatenate((Y, m), axis=1)
    coef = np.linalg.lstsq(Y_, y)[0]

    if a0 is None:
        a = coef[p*N:, :]
        if np.linalg.norm(a) > 0:
            a /= np.linalg.norm(a)
        else:
            a = np.random.randn(L, N)
            a /= np.linalg.norm(a)
    else:
        a = a0.copy()

    if b0 is None:
        b = coef[:p*N, :]
    else:
        b = b0.copy()

    if bias0 is not None:
        bias = bias0.copy()
    else:
        bias = np.zeros(L)

    # initialize rate matrix, rate = E(E(y|x))
    rate = np.empty_like(y)
    updaterate(range(T), range(N))

    # initialize lower bound
    lbound = np.full(maxiter, np.NINF)
    lbound[0] = lowerbound()

    # old values
    old_a = a.copy()
    old_b = b.copy()
    old_bias = bias.copy()
    old_m = m.copy()
    old_V = V.copy()

    # variables for recovery
    b0 = b.copy()
    a0 = a.copy()
    bias0 = bias.copy()
    m0 = m.copy()
    rate0 = rate.copy()

    ra = np.ones(N)
    rb = np.ones(N)
    rm = np.ones(L)
    rbias = 1.0
    dec = 0.5
    inc = 1.5
    thld = 0.75


    it = 1
    convergent = False
    while not convergent and it < maxiter:
        for n in range(N):
        # for n in np.random.permutation(N):
            # beta
            # for _ in range(inneriter):
            grad_b = np.zeros_like(b[:, n])
            hess_b = np.zeros((p * N, p * N))
            for t in range(T):
                grad_b += (y[t, n] - rate[t, n]) * Y[t, :]
                hess_b -= rate[t, n] * np.outer(Y[t, :], Y[t, :])
            if np.linalg.norm(grad_b, ord=np.inf) < eps:
                break
            hess_ = hess_b - hess_adj_b  # Hessain of beta is negative semidefinite. Add a small negative diagonal
            delta_b = -rb[n] * np.linalg.solve(hess_, grad_b)
            # if np.linalg.norm(delta_b, ord=np.inf) < eps:
            #     break
            b0[:, n] = b[:, n]
            rate0[:, n] = rate[:, n]
            predict = np.inner(grad_b, delta_b) + 0.5 * np.dot(delta_b, np.dot(hess_, delta_b))
            print('predicted beta[%d] inc = %.10f' % (n, predict))
            b[:, n] = b[:, n] + delta_b
            updaterate(range(T), [n])
            lb = lowerbound()
            if np.isnan(lb) or lb < lbound[it - 1]:
                rb[n] = dec * rb[n] + eps
                b[:, n] = b0[:, n]
                rate[:, n] = rate0[:, n]
            elif lb - lbound[it - 1] > thld * predict:
                rb[n] *= inc
                if rb[n] > 1:
                    rb[n] = 1.0

        for n in range(N):
        # for n in np.random.permutation(N):
            # alpha
            # for _ in range(inneriter):
            grad_a = np.zeros_like(a[:, n])
            hess_a = np.zeros((L, L))
            for t in range(T):
                Vt = np.diag(V[:, t, t])
                w = m[t, :] + bias + np.dot(Vt, a[:, n])
                grad_a += y[t, n] * (m[t, :] + bias) - rate[t, n] * w
                hess_a -= rate[t, n] * (np.outer(w, w) + Vt)
            # lagrange multiplier
            grad_a_lag = grad_a - np.inner(a[:, n], grad_a) * a[:, n]
            hess_a_lag = hess_a - np.inner(a[:, n], grad_a)
            # If gradient is small enough, stop.
            if np.linalg.norm(grad_a_lag, ord=np.inf) < eps:
                break
            delta_a = -ra[n] * np.linalg.solve(hess_a_lag, grad_a_lag)
            # if np.linalg.norm(delta_a, ord=np.inf) < eps:
            #     break
            a0[:, n] = a[:, n]
            rate0[:, n] = rate[:, n]
            predict = np.inner(grad_a_lag, delta_a) + 0.5 * np.dot(delta_a, np.dot(hess_a_lag, delta_a))
            print('predicted alpha[%d] inc = %.10f' % (n, predict))
            a[:, n] = a[:, n] + delta_a
            updaterate(range(T), [n])
            lb = lowerbound()
            if np.isnan(lb) or lb - lbound[it - 1] < 0:
                ra[n] = dec * ra[n] + eps
                a[:, n] = a0[:, n]
                rate[:, n] = rate0[:, n]
            elif lb - lbound[it - 1] > thld * predict:
                ra[n] *= inc
                if ra[n] > 1:
                    ra[n] = 1.0

        # posterior mean
        for l in range(L):
        # for l in np.random.permutation(L):
            # for _ in range(inneriter):
            grad_m = np.nan_to_num(np.dot(y - rate, a[l, :]) - np.dot(omega[l, :, :], (m[:, l] - mu[:, l])))
            hess_m = np.nan_to_num(-np.diag(np.dot(rate, a[l, :] * a[l, :]))) - omega[l, :, :]
            # grad_m = grad_m * (1 - np.inner(a[l, :],
            #                                 np.linalg.solve(np.outer(a[l, :], a[l, :])
            #                                                 + eps * np.identity(N), a[l, :])))
            if np.linalg.norm(grad_m, ord=np.inf) < eps:
                break
            delta_m = -rm[l] * np.linalg.solve(hess_m, grad_m)
            # if np.linalg.norm(delta_m, ord=np.inf) < eps:
            #     break
            m0[:, l] = m[:, l]
            rate0[:] = rate
            predict = np.inner(grad_m, delta_m) + 0.5 * np.dot(delta_m, np.dot(hess_m, delta_m))
            print('predicted m[%d] inc = %.10f' % (l, predict))
            m[:, l] = m[:, l] + delta_m
            updaterate(range(T), range(N))
            lb = lowerbound()
            if np.isnan(lb) or lb < lbound[it - 1]:
                rm[l] = dec * rm[l] + eps
                m[:, l] = m0[:, l]
                rate[:] = rate0
            elif lb - lbound[it - 1] > thld * predict:
                rm[l] *= inc
                if rm[l] > 1:
                    rm[l] = 1.0

        # posterior covariance
        for l in range(L):
        # for l in np.random.permutation(L):
            # grad_V = -0.5 * np.diag(np.dot(rate, a[l, :] * a[l, :])) - 0.5 * omega[l, :, :] + 0.5 * K[l, :, :]
            rate0[:] = rate
            for t in range(T):
            # for t in np.random.permutation(T):
                k_ = K[l, t, t] - 1 / V[l, t, t]  # \tilde{k}_tt
                old_vtt = V[l, t, t]
                # fixed point iterations
                for _ in range(inneriter):
                    V[l, t, t] = 1 / (omega[l, t, t] - k_ + np.sum(rate[t, :] * a[l, :] * a[l, :]))
                    updaterate([t], range(N))
                # update V
                not_t = np.arange(T) != t
                V[np.ix_([l], not_t, not_t)] = V[np.ix_([l], not_t, not_t)] \
                                               + (V[l, t, t] - old_vtt) \
                                               * np.outer(V[l, t, not_t], V[l, t, not_t]) / (old_vtt * old_vtt)
                V[l, t, not_t] = V[l, not_t, t] = V[l, t, t] * V[l, t, not_t] / old_vtt
                # update k_tt
                K[l, t, t] = k_ + 1 / V[l, t, t]
            # updaterate(range(T), range(N))
            # roll back
            # lb = lowerbound(y, Y, rate, mu, omega, m, V, b, a)
            # if np.isnan(lb) or lb < lbound[it - 1]:
            #     if verbose:
            #         print 'V[%d] failed, lb = %.5f' % (l, lb)
            #     V[l, :, :] = old_V[l, :, :]
            #     rate[:] = rate0

        # bias
        grad_bias = np.dot(a, np.sum(y - rate, axis=0))
        hess_bias = np.dot(a, np.dot(np.diag(np.sum(-rate, axis=0)), a.T))
        if not np.all(hess_bias.diagonal() < 0):
            hess_bias -= eps * np.identity(L)
        delta_bias = -rbias * np.linalg.solve(hess_bias, grad_bias)
        bias0[:] = bias
        rate0[:] = rate
        predict = np.inner(grad_bias, delta_bias) + 0.5 * np.inner(delta_bias, np.dot(hess_bias, delta_bias))
        bias += delta_bias
        updaterate(range(T), range(N))
        lb = lowerbound()
        if np.isnan(lb) or lb < lbound[it - 1]:
            rbias = dec * rbias + eps
            bias[:] = bias0[:]
            rate[:] = rate0[:]
        elif lb - lbound[it - 1] > thld * predict:
            rbias *= inc
            if rbias > 1:
                rbias = 1.0

        # update lower bound
        lbound[it] = lowerbound()

        # check convergence
        delta = max(np.max(np.abs(old_a - a)), np.max(np.abs(old_b - b)), np.max(old_bias - bias),
                    np.max(np.abs(old_m - m)), np.max(np.abs(old_V - V)))

        if delta < tol:
            convergent = True

        if verbose:
            print('Iteration[%d]: L = %.5f delta = %.10f' % (it + 1, lbound[it], delta))

        old_a[:] = a
        old_b[:] = b
        old_m[:] = m
        old_V[:] = V
        old_bias[:] = bias

        it += 1

    if it == maxiter:
        warnings.warn('not convergent', RuntimeWarning)

    stop = time.time()

    return m, V, b, a, bias, lbound[:it], stop - start