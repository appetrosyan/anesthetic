"""Lower-level plotting tools.

Routines that may be of use to users wishing for more fine-grained analyses may
wish to use.

- ``make_1D_axes``
- ``make_2D_axes``

to create a set of axes for plotting on, or

- ``plot_1d``
- ``contour_plot_2d``
- ``scatter_plot_2d``

for directly plotting onto these axes.

"""
import numpy
import pandas
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec as GS, GridSpecFromSubplotSpec as SGS
from anesthetic.kde import kde_1d, kde_2d
from anesthetic.utils import check_bounds
from scipy.interpolate import interp1d
from matplotlib.ticker import MaxNLocator, Locator
from matplotlib.colors import LinearSegmentedColormap


def make_1D_axes(params, **kwargs):
    """Create a set of axes for plotting 1D marginalised posteriors.

    Parameters
    ----------
        params: list(str)
            names of parameters.

        tex: dict(str:str)
            Dictionary mapping params to tex plot labels.
            optional, default params

        fig: matplotlib.figure.Figure
            Figure to plot on
            optional, default last figure matplotlib.pyplot.gcf()

        ncols: int
            Number of columns in the plot
            option, default ceil(sqrt(num_params))

        ticks: integer or matplotlib.ticker.Locator, optional
            Tick preferences for axes. If int, specifies the maximum number
            of ticks. Default: 3

        subplot_spec: matplotlib.gridspec.GridSpec
            gridspec to plot array as part of a subfigure
            optional, default None

    Returns
    -------
    fig: matplotlib.figure.Figure
        New or original (if supplied) figure object

    axes: pandas.Series(matplotlib.axes.Axes)
        Pandas array of axes objects

    """
    tex = kwargs.pop('tex', {})
    fig = kwargs.pop('fig', plt.gcf())
    ncols = kwargs.pop('ncols', int(numpy.ceil(numpy.sqrt(len(params)))))
    nrows = int(numpy.ceil(len(params)/float(ncols)))
    if 'subplot_spec' in kwargs:
        grid = SGS(nrows, ncols, wspace=0,
                   subplot_spec=kwargs.pop('subplot_spec'))
    else:
        grid = GS(nrows, ncols, wspace=0)

    locator = kwargs.pop('ticks', 3)
    if not isinstance(locator, Locator):
        locator = MaxNLocator(locator+1, prune='both')

    if kwargs:
        raise TypeError('Unexpected **kwargs: %r' % kwargs)

    tex = {p: tex[p] if p in tex else p for p in params}
    axes = pandas.Series(index=params, dtype=object)

    for p, g in zip(params, grid):
        axes[p] = ax = fig.add_subplot(g)
        ax.set_xlabel(tex[p])
        ax.set_yticks([])
        ax.xaxis.set_major_locator(locator)

    return fig, axes


def make_2D_axes(params, **kwargs):
    """Create a set of axes for plotting 2D marginalised posteriors.

    Parameters
    ----------
        params: lists of parameters
            Can be either:
            * list(str) if the x and y axes are the same
            * [list(str),list(str)] if the x and y axes are different
            Strings indicate the names of the parameters
            
        tex: dict(str:str), optional
            Dictionary mapping params to tex plot labels.
            Default: params

        upper: None or logical, optional
            Whether to create plots in the upper triangle.
            If None do both. Default: None

        diagonal: True, optional
            Whether to create 1D marginalised plots on the diagonal.
            Default: True

        fig: matplotlib.figure.Figure, optional
            Figure to plot on.
            Default: matplotlib.pyplot.gcf()

        ticks: integer or matplotlib.ticker.Locator, optional
            Tick preferences for axes. If int, specifies the maximum number
            of ticks. Default: 3

        subplot_spec: matplotlib.gridspec.GridSpec, optional
            gridspec to plot array as part of a subfigure.
            Default: None

    Returns
    -------
    fig: matplotlib.figure.Figure
        New or original (if supplied) figure object

    axes: pandas.DataFrame(matplotlib.axes.Axes)
        Pandas array of axes objects

    """
    if len(params) is 2:
        xparams, yparams = params
    else:
        xparams = yparams = params
    axes = pandas.DataFrame(index=numpy.atleast_1d(yparams),
                            columns=numpy.atleast_1d(xparams))
    axes[:][:] = None

    tex = kwargs.pop('tex', {})
    fig = kwargs.pop('fig', plt.gcf())
    if 'subplot_spec' in kwargs:
        grid = SGS(*axes.shape, hspace=0, wspace=0,
                   subplot_spec=kwargs.pop('subplot_spec'))
    else:
        grid = GS(*axes.shape, hspace=0, wspace=0)

    upper = kwargs.pop('upper', None)
    diagonal = kwargs.pop('diagonal', True)
    locator = kwargs.pop('ticks', 3)
    if not isinstance(locator, Locator):
        locator = MaxNLocator(locator+1, prune='both')

    if kwargs:
        raise TypeError('Unexpected **kwargs: %r' % kwargs)

    tex = {p: tex[p] if p in tex else p
           for p in numpy.concatenate((axes.index, axes.columns))}

    all_params = list(axes.index) + list(axes.columns)

    for y, py in enumerate(axes.index):
        for x, px in enumerate(axes.columns):
            _upper = not (px in axes.index and py in axes.columns
                          and all_params.index(px) < all_params.index(py))

            if px == py and not diagonal:
                continue

            if upper == (not _upper) and px != py:
                continue

            if axes[px][py] is None:
                sx = list(axes[px].dropna())
                sx = sx[0] if sx else None
                sy = list(axes.T[py].dropna())
                sy = sy[0] if sy else None
                axes[px][py] = fig.add_subplot(grid[y, x], sharex=sx, sharey=sy)

            axes[px][py]._upper = _upper

    for py, ax in axes.iterrows():
        ax_ = ax.dropna()
        if len(ax_):
            ax_[0].set_ylabel(tex[py])
            ax_[0].yaxis.set_major_locator(locator)
            for a in ax_[1:]:
                a.tick_params('y', left=False, labelleft=False)

    for px, ax in axes.iteritems():
        ax_ = ax.dropna()
        if len(ax_):
            ax_[-1].set_xlabel(tex[px])
            ax_[-1].xaxis.set_major_locator(locator)
            for a in ax_[:-1]:
                a.tick_params('x', bottom=False, labelbottom=False)

    return fig, axes


def plot_1d(ax, data, *args, **kwargs):
    """Plot a 1d marginalised distribution.

    This functions as a wrapper around matplotlib.axes.Axes.plot, with a kernel
    density estimation computation in between. All remaining keyword arguments
    are passed onwards.

    To avoid intefering with y-axis sharing, one-dimensional plots are created
    on a separate axis, which is monkey-patched onto the argument ax as the
    attribute ax.twin.

    Parameters
    ----------
    ax: matplotlib.axes.Axes
        axis object to plot on

    data: numpy.array
        Uniformly weighted samples to generate kernel density estimator.

    xmin, xmax: float
        lower/upper prior bound
        optional, default None

    Returns
    -------
    lines: matplotlib.lines.Line2D
        A list of line objects representing the plotted data (same as
        matplotlib matplotlib.axes.Axes.plot command)

    """
    xmin = kwargs.pop('xmin', None)
    xmax = kwargs.pop('xmax', None)

    if not hasattr(ax, 'twin'):
        ax.twin = ax.twinx()
        ax.twin.set_yticks([])
        ax.twin.set_ylim(0, 1.1)
        if not ax.is_first_col():
            ax.tick_params('y', left=False)

    x, p = kde_1d(data, xmin, xmax)
    p /= p.max()
    i = (p >= 1e-2)

    ans = ax.twin.plot(x[i], p[i], *args, **kwargs)
    ax.twin.set_xlim(*check_bounds(x[i], xmin, xmax), auto=True)
    return ans


def contour_plot_2d(ax, data_x, data_y, *args, **kwargs):
    """Plot a 2d marginalised distribution as contours.

    This functions as a wrapper around matplotlib.axes.Axes.contour, and
    matplotlib.axes.Axes.contourf with a kernel density estimation computation
    in between. All remaining keyword arguments are passed onwards to both
    functions.

    Parameters
    ----------
    ax: matplotlib.axes.Axes
        axis object to plot on

    data_x, data_y: numpy.array
        x and y coordinates of uniformly weighted samples to generate kernel
        density estimator.

    xmin, xmax, ymin, ymax: float
        lower/upper prior bounds in x/y coordinates
        optional, default None

    Returns
    -------
    c: matplotlib.contour.QuadContourSet
        A set of contourlines or filled regions

    """
    xmin = kwargs.pop('xmin', None)
    xmax = kwargs.pop('xmax', None)
    ymin = kwargs.pop('ymin', None)
    ymax = kwargs.pop('ymax', None)
    color = kwargs.pop('color', next(ax._get_lines.prop_cycler)['color'])

    x, y, pdf = kde_2d(data_x, data_y,
                       xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)
    pdf /= pdf.max()
    p = sorted(pdf.flatten())
    m = numpy.cumsum(p)
    m /= m[-1]
    interp = interp1d([0]+list(m)+[1], [0]+list(p)+[1])
    contours = list(interp([0.05, 0.33]))+[1]

    # Correct non-zero edges
    if min(p) != 0:
        contours = [min(p)] + contours

    # Correct level sets
    for i in range(1, len(contours)):
        if contours[i-1] == contours[i]:
            for j in range(i):
                contours[j] = contours[j] - 1e-5

    i = (pdf >= 1e-2).any(axis=0)
    j = (pdf >= 1e-2).any(axis=1)

    cmap = LinearSegmentedColormap.from_list(color, ['#ffffff', color])
    zorder = max([child.zorder for child in ax.get_children()])

    cbar = ax.contourf(x[i], y[j], pdf[numpy.ix_(j, i)], contours,
                       vmin=0, vmax=1.0, cmap=cmap, zorder=zorder+1,
                       *args, **kwargs)
    ax.contour(x[i], y[j], pdf[numpy.ix_(j, i)], contours,
               vmin=0, vmax=1.2, linewidths=0.5, colors='k', zorder=zorder+2,
               *args, **kwargs)
    ax.set_xlim(*check_bounds(x[i], xmin, xmax), auto=True)
    ax.set_ylim(*check_bounds(y[j], ymin, ymax), auto=True)
    return cbar


def scatter_plot_2d(ax, data_x, data_y, *args, **kwargs):
    """Plot samples from a 2d marginalised distribution.

    This functions as a wrapper around matplotlib.axes.Axes.plot, enforcing any
    prior bounds. All remaining keyword arguments are passed onwards.

    Parameters
    ----------
    ax: matplotlib.axes.Axes
        axis object to plot on

    data_x, data_y: numpy.array
        x and y coordinates of uniformly weighted samples to generate kernel
        density estimator.

    xmin, xmax, ymin, ymax: float
        lower/upper prior bounds in x/y coordinates
        optional, default None

    Returns
    -------
    lines: matplotlib.lines.Line2D
        A list of line objects representing the plotted data (same as
        matplotlib matplotlib.axes.Axes.plot command)

    """
    xmin = kwargs.pop('xmin', None)
    xmax = kwargs.pop('xmax', None)
    ymin = kwargs.pop('ymin', None)
    ymax = kwargs.pop('ymax', None)

    points = ax.plot(data_x, data_y, 'o', markersize=1, *args, **kwargs)
    ax.set_xlim(*check_bounds(data_x, xmin, xmax), auto=True)
    ax.set_ylim(*check_bounds(data_y, ymin, ymax), auto=True)
    return points
