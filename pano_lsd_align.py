'''
Most of the code are modified from LayoutNet official's matlab code
in which some of the code are borrowed from PanoContext and PanoBasic

All functions, naming rule and data flow follow official
for easier converting and comparing.
Code is not optimized for python or numpy yet.

author: Cheng Sun
email : s2821d3721@gmail.com
'''
import numpy as np
from scipy.ndimage import map_coordinates
from pano import coords2uv, uv2xyzN, xyz2uvN, computeUVN
import cv2


def warpImageFast(im, XXdense, YYdense):
    minX = max(1., np.floor(XXdense.min()) - 1)
    minY = max(1., np.floor(YYdense.min()) - 1)

    maxX = min(im.shape[1], np.ceil(XXdense.max()) + 1)
    maxY = min(im.shape[0], np.ceil(YYdense.max()) + 1)

    im = im[int(round(minY-1)):int(round(maxY)),
            int(round(minX-1)):int(round(maxX))]

    assert XXdense.shape == YYdense.shape
    out_shape = XXdense.shape
    coordinates = [
        (YYdense - minY).reshape(-1),
        (XXdense - minX).reshape(-1),
    ]
    im_warp = np.stack([
        map_coordinates(im[..., c], coordinates, order=1).reshape(out_shape)
        for c in range(im.shape[-1])],
        axis=-1)

    return im_warp


def rotatePanorama(img, vp=None, R=None):
    '''
    Rotate panorama
        if R is given, vp (vanishing point) will be overlooked
        otherwise R is computed from vp
    '''
    sphereH, sphereW, C = img.shape

    # new uv coordinates
    TX, TY = np.meshgrid(range(1, sphereW + 1), range(1, sphereH + 1))
    TX = TX.reshape(-1, 1, order='F')
    TY = TY.reshape(-1, 1, order='F')
    ANGx = (TX - sphereW/2 - 0.5)/sphereW * np.pi * 2
    ANGy = -(TY - sphereH/2 - 0.5)/sphereH * np.pi
    uvNew = np.hstack([ANGx, ANGy])
    xyzNew = uv2xyzN(uvNew, 1)

    # rotation matrix
    if R is None:
        R = np.linalg.inv(vp.T)

    xyzOld = np.linalg.solve(R, xyzNew.T).T
    uvOld = xyz2uvN(xyzOld, 1)

    Px = (uvOld[:, 0] + np.pi) / (2*np.pi) * sphereW + 0.5
    Py = (-uvOld[:, 1] + np.pi/2) / np.pi * sphereH + 0.5

    Px = Px.reshape(sphereH, sphereW, order='F')
    Py = Py.reshape(sphereH, sphereW, order='F')

    # boundary
    imgNew = np.zeros((sphereH+2, sphereW+2, C), np.float64)
    imgNew[1:-1, 1:-1, :] = img
    imgNew[1:-1, 0, :] = img[:, -1, :]
    imgNew[1:-1, -1, :] = img[:, 0, :]
    imgNew[0, 1:sphereW//2+1, :] = img[0, sphereW-1:sphereW//2-1:-1, :]
    imgNew[0, sphereW//2+1:-1, :] = img[0, sphereW//2-1::-1, :]
    imgNew[-1, 1:sphereW//2+1, :] = img[-1, sphereW-1:sphereW//2-1:-1, :]
    imgNew[-1, sphereW//2+1:-1, :] = img[0, sphereW//2-1::-1, :]
    imgNew[0, 0, :] = img[0, 0, :]
    imgNew[-1, -1, :] = img[-1, -1, :]
    imgNew[0, -1, :] = img[0, -1, :]
    imgNew[-1, 0, :] = img[-1, 0, :]

    rotImg = warpImageFast(imgNew, Px+1, Py+1)

    return rotImg


def imgLookAt(im, CENTERx, CENTERy, new_imgH, fov):
    sphereH = im.shape[0]
    sphereW = im.shape[1]
    warped_im = np.zeros((new_imgH, new_imgH, 3))
    TX, TY = np.meshgrid(range(1, new_imgH + 1), range(1, new_imgH + 1))
    TX = TX.reshape(-1, 1, order='F')
    TY = TY.reshape(-1, 1, order='F')
    TX = TX - 0.5 - new_imgH/2
    TY = TY - 0.5 - new_imgH/2
    r = new_imgH / 2 / np.tan(fov/2)

    # convert to 3D
    R = np.sqrt(TY ** 2 + r ** 2)
    ANGy = np.arctan(- TY / r)
    ANGy = ANGy + CENTERy

    X = np.sin(ANGy) * R
    Y = -np.cos(ANGy) * R
    Z = TX

    INDn = np.nonzero(np.abs(ANGy) > np.pi/2)

    # project back to sphere
    ANGx = np.arctan(Z / -Y)
    RZY = np.sqrt(Z ** 2 + Y ** 2)
    ANGy = np.arctan(X / RZY)

    ANGx[INDn] = ANGx[INDn] + np.pi
    ANGx = ANGx + CENTERx

    INDy = np.nonzero(ANGy < -np.pi/2)
    ANGy[INDy] = -np.pi - ANGy[INDy]
    ANGx[INDy] = ANGx[INDy] + np.pi

    INDx = np.nonzero(ANGx <= -np.pi);   ANGx[INDx] = ANGx[INDx] + 2 * np.pi
    INDx = np.nonzero(ANGx >   np.pi);   ANGx[INDx] = ANGx[INDx] - 2 * np.pi
    INDx = np.nonzero(ANGx >   np.pi);   ANGx[INDx] = ANGx[INDx] - 2 * np.pi
    INDx = np.nonzero(ANGx >   np.pi);   ANGx[INDx] = ANGx[INDx] - 2 * np.pi

    Px = (ANGx + np.pi) / (2*np.pi) * sphereW + 0.5
    Py = ((-ANGy) + np.pi/2) / np.pi * sphereH + 0.5

    INDxx = np.nonzero(Px < 1)
    Px[INDxx] = Px[INDxx] + sphereW
    im = np.concatenate([im, im[:, :2]], 1)

    Px = Px.reshape(new_imgH, new_imgH, order='F')
    Py = Py.reshape(new_imgH, new_imgH, order='F')

    warped_im = warpImageFast(im, Px, Py)

    return warped_im


def separatePano(panoImg, fov, x, y, imgSize=320):
    '''cut a panorama image into several separate views'''
    assert x.shape == y.shape
    if not isinstance(fov, np.ndarray):
        fov = fov * np.ones_like(x)

    sepScene = [
        {
            'img': imgLookAt(panoImg.copy(), xi, yi, imgSize, fovi),
            'vx': xi,
            'vy': yi,
            'fov': fovi,
            'sz': imgSize,
        }
        for xi, yi, fovi in zip(x, y, fov)
    ]

    return sepScene


def lsdWrap(img, LSD=None, **kwargs):
    '''
    Opencv implementation of
    Rafael Grompone von Gioi, Jérémie Jakubowicz, Jean-Michel Morel, and Gregory Randall,
    LSD: a Line Segment Detector, Image Processing On Line, vol. 2012.
    [Rafael12] http://www.ipol.im/pub/art/2012/gjmr-lsd/?utm_source=doi
    @img
        input image
    @LSD
        Constructing by cv2.createLineSegmentDetector
        https://docs.opencv.org/3.0-beta/modules/imgproc/doc/feature_detection.html#linesegmentdetector
        if LSD is given, kwargs will be ignored
    @kwargs
        is used to construct LSD
        work only if @LSD is not given
    '''
    if LSD is None:
        LSD = cv2.createLineSegmentDetector(**kwargs)

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    lines, width, prec, nfa = LSD.detect(img)
    lines = np.squeeze(lines, 1)
    edgeList = np.concatenate([lines, width, prec, nfa], 1)
    edgeMap = LSD.drawSegments(np.zeros_like(img), lines)[..., -1]
    return edgeMap, edgeList


def edgeFromImg2Pano(edge):
    edgeList = edge['edgeLst']
    if len(edgeList) == 0:
        return np.array([])

    vx = edge['vx']
    vy = edge['vy']
    fov = edge['fov']
    imH, imW = edge['img'].shape

    R = (imW/2) / np.tan(fov/2)

    # im is the tangent plane, contacting with ball at [x0 y0 z0]
    x0 = R * np.cos(vy) * np.sin(vx)
    y0 = R * np.cos(vy) * np.cos(vx)
    z0 = R * np.sin(vy)
    vecposX = np.array([np.cos(vx), -np.sin(vx), 0])
    vecposY = np.cross(np.array([x0, y0, z0]), vecposX)
    vecposY = vecposY / np.sqrt(vecposY @ vecposY.T)
    Xc = (0 + imW-1) / 2
    Yc = (0 + imH-1) / 2

    vecx1 = (edgeList[:, 0] - Xc).reshape(-1, 1)
    vecy1 = (edgeList[:, 1] - Yc).reshape(-1, 1)
    vecx2 = (edgeList[:, 2] - Xc).reshape(-1, 1)
    vecy2 = (edgeList[:, 3] - Yc).reshape(-1, 1)

    vec1 = np.tile(vecx1, [1, 3]) * np.tile(vecposX, [len(vecx1), 1]) \
         + np.tile(vecy1, [1, 3]) * np.tile(vecposY, [len(vecy1), 1])
    vec2 = np.tile(vecx2, [1, 3]) * np.tile(vecposX, [len(vecx2), 1]) \
         + np.tile(vecy2, [1, 3]) * np.tile(vecposY, [len(vecy2), 1])
    coord1 = np.tile([x0, y0, z0], [len(vec1), 1]) + vec1
    coord2 = np.tile([x0, y0, z0], [len(vec2), 1]) + vec2

    normal = np.cross(coord1, coord2, axis=1)
    n = np.sqrt(normal[:, 0] ** 2 + normal[:, 1] ** 2 + normal[:, 2] ** 2)
    normal = normal / n.reshape(-1, 1)

    panoList = np.concatenate([normal, coord1, coord2, edgeList[:, -1].reshape(-1, 1)], 1)

    return panoList


def panoEdgeDetection(img, viewSize=320, qError=2.0):
    '''
    line detection on panorama
       INPUT:
           img: image waiting for detection, double type, range 0~1
           viewSize: image size of croped views
           qError: set smaller if more line segment wanted
       OUTPUT:
           oLines: detected line segments
           vp: vanishing point
           views: separate views of panorama
           edges: original detection of line segments in separate views
           panoEdge: image for visualize line segments
    '''
    cutSize = viewSize
    fov = np.pi / 3
    xh = np.arange(-np.pi, np.pi*5/6, np.pi/6)
    yh = np.zeros(xh.shape[0])
    xp = np.array([-3/3, -2/3, -1/3, 0/3,  1/3, 2/3, -3/3, -2/3, -1/3,  0/3,  1/3,  2/3]) * np.pi
    yp = np.array([ 1/4,  1/4,  1/4, 1/4,  1/4, 1/4, -1/4, -1/4, -1/4, -1/4, -1/4, -1/4]) * np.pi
    x = np.concatenate([xh, xp, [0, 0]])
    y = np.concatenate([yh, yp, [np.pi/2., -np.pi/2]])

    sepScene = separatePano(img.copy(), fov, x, y, cutSize)
    for i in range(len(sepScene)):
        Image.fromarray(sepScene[i]['img']).save('test/edgeMap/%02d_scene_.png' % (i+1))
    edge = []
    LSD = cv2.createLineSegmentDetector(_refine=cv2.LSD_REFINE_ADV, _quant=qError)
    for i, scene in enumerate(sepScene):
        edgeMap, edgeList = lsdWrap(scene['img'], LSD)
        Image.fromarray(edgeMap).save('test/edgeMap/%02d.out.png' % (i+1))
        edge.append({
            'img': edgeMap,
            'edgeLst': edgeList,
            'vx': scene['vx'],
            'vy': scene['vy'],
            'fov': scene['fov'],
        })
        edge[-1]['panoLst'] = edgeFromImg2Pano(edge[-1])


if __name__ == '__main__':

    from PIL import Image
    img_ori = Image.open('test/pano_arrsorvpjptpii.jpg')

    # Test separatePano
    panoEdgeDetection(np.array(img_ori))

    # Test rotatePanorama
    img_rotatePanorama = np.array(Image.open('test/rotatePanorama_pano_arrsorvpjptpii.png'))
    vp = np.array([
        [0.758831, -0.651121, 0.014671],
        [0.650932, 0.758969, 0.015869],
        [-0.018283, 0.001220, 0.999832]])
    img_rotatePanorama_ = rotatePanorama(np.array(img_ori.resize((2048, 1024))) / 255.0, vp)
    img_rotatePanorama_ = (img_rotatePanorama_ * 255.0).round()
    assert img_rotatePanorama_.shape == img_rotatePanorama.shape
    print('rotatePanorama: L1  diff', np.abs(img_rotatePanorama - img_rotatePanorama_.round()).mean())
    print('rotatePanorama: max diff', np.abs(img_rotatePanorama - img_rotatePanorama_.round()).max())
    Image.fromarray(img_rotatePanorama_.round().astype(np.uint8)) \
         .save('test/rotatePanorama_pano_arrsorvpjptpii.out.png')
