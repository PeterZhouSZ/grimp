#!/bin/python

from scipy import *
from scipy.linalg import *
from scipy.ndimage import *
from numpy.fft import fft2, ifft2, fftshift
from scipy.signal import convolve2d as conv
from scipy.special import *
import matplotlib.pyplot as plt
from time import clock
import networkx as nx
import Image
import community
        
def process_image(im, patch_size=8):
    """
    This routine will process the image and return the separate channels. The
    channels will be Y, Cb, Cr. This routine is used by create_feature_vector.
    """
    
    imR = im[:,:,0]
    imG = im[:,:,1]
    imB = im[:,:,2]

    x, y = imR.shape
    residX = x % patch_size
    residY = y % patch_size

    xdim = x - residX
    ydim = y - residY

    # As of now, we will just adjust the image brutely so that dimensions are
    # multiples of patch size
    imR = imR[:xdim, :ydim]
    imG = imG[:xdim, :ydim]
    imB = imB[:xdim, :ydim]

    # Create the Y, Cb and Cr channels
    imY = 0.229*imR + 0.587*imG + 0.114*imB
    imCb = 128 - 0.168763*imR - 0.331264*imG - 0.5*imB
    imCr = 128 + 0.5*imR - 0.418688*imG - 0.081312*imB

    return [imY, imCb, imCr]

def create_feature_vector(im, patch_size=8):
    """
    This routine creates the feature vector for the image. The following are
    the features chosen as of now:
    1. Y value
    2. Cb value
    3. Cr value
    4. Position
    5. Patch entropy
    """
    imY, imCb, imCr = im
    xdim, ydim = imY.shape
    iterx = xdim / patch_size
    itery = ydim / patch_size
    fvector = []

    # We need to create differentiating kernels for finding orientation
    # histogram. 
    kernx = array([-1, 0, 1,
                   -1, 0, 1,
                   -1, 0, 1]).reshape(3,3)
    kerny = array([-1, -1, -1,
                    0,  0,  0,
                    1,  1,  1]).reshape(3,3)
    for i in range(iterx):
        for j in range(itery):
            x1 = i * patch_size
            y1 = j * patch_size
            x2 = x1 + patch_size
            y2 = y1 + patch_size

            imchunkY = imY[x1:x2, y1:y2]
            imchunkCb = imCb[x1:x2, y1:y2]
            imchunkCr = imCr[x1:x2, y1:y2]

            # Calculation of Y Cb Cr from R G B is from wikipedia:
            # http://en.wikipedia.org/wiki/YCbCr
            Y = sum(imchunkY) / (patch_size * patch_size)
            Cb = sum(imchunkCb) / (patch_size * patch_size)
            Cr = sum(imchunkCr) / (patch_size * patch_size)

            # Next feature should be the position of the patch
            xpos = (x1 + x2)/2
            ypos = (y1 + y2)/2
            pos = [xpos, ypos]

            # We need to now calculate the orientation histogram. We will use
            # differentiation operator for the same
            imchunk = imchunkY
            imx = conv(imchunk, kernx)
            imy = conv(imchunk, kerny)
            grad = 180 + 180*arctan2(imy, imx)/3.1415926

            # We will now segregate our gradient map into bins
            bin_len_l = 0
            bin_len_h = 0
            hist = []
            for k in range(9):
                bin_len_l = bin_len_h
                bin_len_h += 40
                x, y = where((imchunk <= bin_len_h)*(imchunk > bin_len_l))
                hist.append(len(x))
            H = array(hist)
            x = where(H == 0)
            H[x] = 1

            # Entropy formula is emperical(For us!)
            entropy = sum(H * log(H))

            fvector.append([Y, Cb, Cr, pos, entropy])
    return fvector

def create_graph(fvector, xdim, ydim):
    """
        Create the image graph from the feature vectors.
    """
    node_count = len(fvector)
    imgraph = nx.Graph()
    for i in range(node_count):
        Y, Cb, entropy, pos, Cr = fvector[i]
        imgraph.add_node(i, Y=Y, Cb = Cb, Cr = Cr,
                         pos=pos, entropy=entropy)
        
    # We have created the nodes. Now we need to create the edges. As of now,
    # our edge weight is exp(-(f2^2 - f1^2))*100/distance where f1, f2 are the correspondin
    # vertices featrues except distance between them.
    
    for i in range(node_count):
        for j in range(i+1, node_count):
            
            Y1 = imgraph.node[i]['Y']
            Y2 = imgraph.node[j]['Y']
            Cb1 = imgraph.node[i]['Cb']
            Cb2 = imgraph.node[j]['Cb']
            Cr1 = imgraph.node[i]['Cr']
            Cr2 = imgraph.node[j]['Cr']
            x1,y1 = imgraph.node[i]['pos']
            x2,y2 = imgraph.node[j]['pos']
            E1 = imgraph.node[i]['entropy']
            E2 = imgraph.node[j]['entropy']

            v1 = array([Y2-Y1, Cb2-Cb1, Cr2-Cr1, E2-E1])
            dist_max = hypot(xdim, ydim)
            dist = hypot(x2-x2, y2-y1)
            #weight = exp(-1 * dot(v1, v1.T))*(dist_max / (1 + dist))
            weight = exp(-1 * dot(v1, v1.T))
            if weight > 10e-10:
                #print weight
                imgraph.add_edge(i, j, weight=weight)
    return imgraph

def process_graph(imgraph, partition):
    """
    This routine will process the graph and attempt to divide it into
    communities.
    """

    # The values of the partition will represent the community to which they
    # belong. The keys are the node numbers.
    
    n_communities = max(partition.values()) + 1
    n_nodes = len(partition)
    communities = range(n_communities)

    # The next one is a sad hack. Need to find an elegant way.
    for i in range(n_communities):
        communities[i] = []
        
    for i in range(n_nodes):
        communities[partition[i]].append(i)
        
    return communities

def save_partition_snapshot(imgraph, partition):
    """
    Save the partition shapshot. This is just for reference.
    """
    size = float(len(set(partition.values())))
    pos = nx.spring_layout(imgraph)
    count = 0.
    for com in set(partition.values()) :
        count = count + 1.
        list_nodes = [nodes for nodes in partition.keys()
                                    if partition[nodes] == com]
        nx.draw_networkx_nodes(imgraph, pos, list_nodes, node_size = 20,
                                    node_color = str(count / size))

    nx.draw_networkx_edges(imgraph,pos, alpha=0.5)
    plt.savefig('images/__partition_snapshot.png')

def draw_line(im, point1, point2):
    """
        Routine to draw a line between two images in a ndimage array.
        This can also be done in PIL image, but it may take time to convert
        from ndarray to PIL and back again
    """
    x1, y1 = point1
    x2, y2 = point2

    dist = hypot(x2-x1, y2-y1)
    theta = arctan2(y2-y1, x2-x1)

    r = array(range(int(dist +1)))
    x = x1 + r * cos(theta)
    y = y1 + r * sin(theta)
    x = x.astype(int)
    y = y.astype(int)
    im[x, y] = 0
    im[x1-1:x1+1, y1-1:y1+1] = [255,0,0]
    im[x2-1:x2+1, y2-1:y2+1] = [255,0,0]

    return im

im = imread('random.jpg')
im_processed = process_image(im)
fvector = create_feature_vector(im_processed)
imgraph = create_graph(fvector, im.shape[1], im.shape[2])

partition = community.best_partition(imgraph)
comm = process_graph(imgraph, partition)

positions = []
for group in comm:
    pos = []
    old_pos = None
    for index in group:
        x, y = imgraph.node[index]['pos']
        pos.append([x, y])
        if old_pos == None:
            old_pos = [x, y]
            im[x-2:x+2, y-2:y+2] = [0,0,255]
        else:
            im = draw_line(im, old_pos, [x, y])
            old_pos = [x, y]
    im[x-2:x+2, y-2:y+2] = [255,255,0]
    positions.append(pos)

count = 0
for t in positions:
    t = array(t)
    x1 = min(t[:,0])
    x2 = max(t[:,0])
    y1 = min(t[:,1])
    y2 = max(t[:,1])
    im1 = copy(im)
    im1[x1:x2, y1] = 0
    im1[x1:x2, y2] = 0
    im1[x1, y1:y2] = 0
    im1[x2, y1:y2] = 0
    Image.fromarray(im1).convert('RGB').save('images/im'+str(count)+'.jpg')
    count += 1
Image.fromarray(im).show()
#save_partition_snapshot(imgraph, partition)