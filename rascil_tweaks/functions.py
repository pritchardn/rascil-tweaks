# === RASCIL imports required for function overrides ====
# RASCIL needs to be installed as well in order for this
# to work.
import logging
from collections.abc import Sequence
from typing import Any

import astropy.units as units
import astropy.wcs as wcs
import numpy
from rascil.data_models.memory_data_models import BlockVisibility, Image
from rascil.data_models.parameters import get_parameter
from rascil.data_models.polarisation import PolarisationFrame
from rascil.processing_components.fourier_transforms import ifft
from rascil.processing_components.image.operations import (
    create_image_from_array,
)

log = logging.getLogger("rascil-logger")


def griddataExtract(griddata: Sequence, index: int = 0) -> Any:
    return griddata[index]


def phasecentreExtract(vis) -> Any:
    return vis.phasecentre


def visExtract(vis: Sequence, index: int = 0) -> Any:
    return vis[index]


def polFrameExtract(vis) -> Any:
    return vis._polarisation_frame


def wcsExtract(im):
    return im.image_acc.wcs


def polarisation_frame_from_names(names):
    """Derive polarisation_name from names

    :param names:
    :return:
    """
    if (
        isinstance(names, str)
        and names in PolarisationFrame.polarisation_frames
    ):
        return PolarisationFrame(names)
    elif isinstance(names, list):
        for frame in PolarisationFrame.polarisation_frames.keys():
            frame_names = PolarisationFrame(frame).names
            if sorted(names) == sorted(frame_names):
                return PolarisationFrame(frame)
    raise ValueError("Polarisation {} not supported".format(names))


def fft_griddata_to_image(griddata, template, gcf=None, wcs=None):
    """FFT griddata after applying gcf

    If imaginary is true the data array is complex

    :param griddata:
    :param gcf: Grid correction image
    :return:
    """
    # assert isinstance(griddata, GridData)

    ny, nx = (
        griddata["pixels"].data.shape[-2],
        griddata["pixels"].data.shape[-1],
    )

    if gcf is None:
        im_data = ifft(griddata["pixels"].data) * float(nx) * float(ny)
    else:
        im_data = (
            ifft(griddata["pixels"].data)
            * gcf["pixels"].data
            * float(nx)
            * float(ny)
        )
    if wcs is None:
        wcs = template.image_acc.wcs
    return create_image_from_array(
        im_data, wcs, griddata.griddata_acc.polarisation_frame
    )


def create_image_from_visibility(vis: BlockVisibility, **kwargs) -> Image:
    """Make an empty image from params and BlockVisibility

    This makes an empty, template image consistent with the visibility,
    allowing optional overriding of select parameters. This is a convenience
    function and does not transform the visibilities.

    :param vis:
    :param phasecentre: Phasecentre (Skycoord)
    :param channel_bandwidth: Channel width (Hz)
    :param cellsize: Cellsize (radians)
    :param npixel: Number of pixels on each axis (512)
    :param frame: Coordinate frame for WCS (ICRS)
    :param equinox: Equinox for WCS (2000.0)
    :param nchan: Number of image channels (Default is 1 -> MFS)
    :return: image

    See also
        :py:func:`rascil.processing_components.image.operations.create_image`
    """
    log.debug(
        "create_image_from_visibility: Parsing parameters to get definition"
        + "of WCS"
    )

    imagecentre = get_parameter(kwargs, "imagecentre", vis.phasecentre)
    phasecentre = get_parameter(kwargs, "phasecentre", vis.phasecentre)

    # Spectral processing options
    ufrequency = numpy.unique(vis["frequency"].data)
    frequency = get_parameter(kwargs, "frequency", vis["frequency"].data)

    vnchan = len(ufrequency)

    inchan = get_parameter(kwargs, "nchan", vnchan)
    reffrequency = frequency[0] * units.Hz
    channel_bandwidth = (
        get_parameter(
            kwargs, "channel_bandwidth", vis["channel_bandwidth"].data.flat[0]
        )
        * units.Hz
    )

    if (inchan == vnchan) and vnchan > 1:
        log.debug(
            "create_image_from_visibility: Defining %d channel Image at %s,"
            " starting frequency %s, and bandwidth %s"
            % (inchan, imagecentre, reffrequency, channel_bandwidth)
        )
    elif (inchan == 1) and vnchan > 1:
        assert (
            numpy.abs(channel_bandwidth) > 0.0
        ), "Channel width must be non-zero for mfs mode"
        log.debug(
            "create_image_from_visibility: Defining single channel MFS Image"
            " at %s, starting frequency %s, "
            "and bandwidth %s" % (imagecentre, reffrequency, channel_bandwidth)
        )
    elif inchan > 1 and vnchan > 1:
        assert (
            numpy.abs(channel_bandwidth) > 0.0
        ), "Channel width must be non-zero for mfs mode"
        log.debug(
            "create_image_from_visibility: Defining multi-channel MFS Image"
            " at %s, starting frequency %s, "
            "and bandwidth %s" % (imagecentre, reffrequency, channel_bandwidth)
        )
    elif (inchan == 1) and (vnchan == 1):
        assert (
            numpy.abs(channel_bandwidth) > 0.0
        ), "Channel width must be non-zero for mfs mode"
        log.debug(
            "create_image_from_visibility: Defining single channel Image"
            " at %s, starting frequency %s, "
            "and bandwidth %s" % (imagecentre, reffrequency, channel_bandwidth)
        )
    else:
        raise ValueError(
            "create_image_from_visibility: unknown spectral mode inchan = {}, "
            "vnchan = {} ".format(inchan, vnchan)
        )

    # Image sampling options
    npixel = get_parameter(kwargs, "npixel", 512)
    uvmax = numpy.max((numpy.abs(vis["uvw_lambda"].data[..., 0:2])))
    log.debug("create_image_from_visibility: uvmax = %f wavelengths" % uvmax)
    criticalcellsize = 1.0 / (uvmax * 2.0)
    log.debug(
        "create_image_from_visibility: Critical cellsize = %f radians, %f "
        "degrees" % (criticalcellsize, criticalcellsize * 180.0 / numpy.pi)
    )
    cellsize = get_parameter(kwargs, "cellsize", 0.5 * criticalcellsize)
    log.debug(
        "create_image_from_visibility: Cellsize          = %g radians, %g "
        "degrees" % (cellsize, cellsize * 180.0 / numpy.pi)
    )
    override_cellsize = get_parameter(kwargs, "override_cellsize", True)
    if (override_cellsize and cellsize > criticalcellsize) or (
        cellsize == 0.0
    ):
        log.debug(
            "create_image_from_visibility: Resetting cellsize %g radians "
            "to criticalcellsize %g radians" % (cellsize, criticalcellsize)
        )
        cellsize = criticalcellsize
    pol_frame = get_parameter(
        kwargs,
        "polarisation_frame",
        PolarisationFrame(vis._polarisation_frame),
    )
    inpol = pol_frame.npol

    # Now we can define the WCS, which is a convenient place to hold the info
    # above Beware of python indexing order! wcs and the array have opposite
    # ordering
    shape = [inchan, inpol, npixel, npixel]
    log.debug("create_image_from_visibility: image shape is %s" % str(shape))
    w = wcs.WCS(naxis=4)
    # The negation in the longitude is needed by definition of RA, DEC
    w.wcs.cdelt = [
        -cellsize * 180.0 / numpy.pi,
        cellsize * 180.0 / numpy.pi,
        1.0,
        channel_bandwidth.to(units.Hz).value,
    ]
    # The numpy definition of the phase centre of an FFT is n // 2 (0 - rel)
    # so that's what we use for
    # the reference pixel. We have to use 0 rel everywhere.
    w.wcs.crpix = [npixel // 2 + 1, npixel // 2 + 1, 1.0, 1.0]
    w.wcs.ctype = ["RA---SIN", "DEC--SIN", "STOKES", "FREQ"]
    w.wcs.crval = [
        phasecentre.ra.deg,
        phasecentre.dec.deg,
        1.0,
        reffrequency.to(units.Hz).value,
    ]
    w.naxis = 4

    w.wcs.radesys = get_parameter(kwargs, "frame", "ICRS")
    w.wcs.equinox = get_parameter(kwargs, "equinox", 2000.0)

    chunksize = get_parameter(kwargs, "chunksize", None)
    im = create_image_from_array(
        numpy.zeros(shape),
        wcs=w,
        polarisation_frame=pol_frame,
        chunksize=chunksize,
    )
    return im
