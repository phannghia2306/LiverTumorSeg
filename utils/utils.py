import nibabel as nib
import cv2
import numpy as np
import matplotlib.pyplot as plt
import os
from tensorflow import keras
import matplotlib.pyplot as plt
from skimage.measure import label

"""Preprocess"""
def neuroToRadio(vol, flip_flag):
    """ Change from neurological to radiological orientation. """
    vol = np.transpose(vol, axes=(1, 0, 2))
    if flip_flag:
        vol = np.fliplr(vol)
    vol = np.flipud(vol)

    return vol

def adjust_HU_value(volume, x=240, y=-160):
    # The upper grey level x and the lower grey level y
    volume[volume > x] = x  # above x will be white 
    volume[volume < y] = y  # below y will be black
    return volume
    
def normalize(volume):
    # Normalize into range [0, 1]
    vol_max = volume.max()
    vol_min = volume.min()
    volume = (volume - vol_min) / (vol_max - vol_min)
    return volume

def nifti_to_png(nifti_path, file_name, png_path, ct=False, liver_seg=False, tumor_seg=False):
    volume_path = os.path.join(nifti_path, file_name)
    load_volume = nib.load(volume_path)

    volume = neuroToRadio(load_volume.get_fdata(), 0)
    # w, h: slice size; d: number of slices in volume
    (w, h, d) = volume.shape

    if ct: # Save CT images
        # HU value adjusment
        adj_vol = adjust_HU_value(volume)
        # Normalize volume into range [0, 1]
        norm_vol = normalize(adj_vol)
        for i in range(d):
            slice = norm_vol[:,:,i] * 65535
            slice_path = os.path.join(png_path, file_name.replace('.nii', '_' + str(i) + '.png'))
            cv2.imwrite(slice_path, slice.astype(np.uint16)) 
    
    elif liver_seg: # Save liver segmentations
        volume[volume >= 1] = 1
        for i in range(d):
            slice = volume[:,:,i] * 255
            slice_path = os.path.join(png_path, file_name.replace('.nii', '_' + str(i) + '.png'))
            cv2.imwrite(slice_path, slice)
    
    elif tumor_seg: # Save tumor segmentations
        volume[volume == 1] = 0
        volume[volume == 2] = 1 
        for i in range(d):
            slice = volume[:,:,i] * 255
            slice_path = os.path.join(png_path, file_name.replace('.nii', '_' + str(i) + '.png'))
            cv2.imwrite(slice_path, slice)
    else:
        print('Correct the parameters!')

def nifti_to_array(file_path):
    volume = nib.load(file_path)
    volume = volume.get_fdata()
    (w, h, d) = volume.shape
    array = np.zeros((d, w, h, 3))
    volume = adjust_HU_value(volume)
    volume = neuroToRadio(volume, flip_flag=False)
    volume = normalize(volume)
    volume = volume * 255
    volume = volume.astype(np.uint8)
    for i in range(d):
        array[i] = cv2.cvtColor(volume[:,:,i], cv2.COLOR_GRAY2BGR)
        array[i] = normalize(array[i])
    return array

def convert_volume_to_nifti(seg_arr, origin_file_path, filename, output_dir):
    origin_volume = nib.load(origin_file_path)
    (w, h, d) = origin_volume.shape
    seg_vol = np.zeros((w, h, d)).astype('uint8')
    for i in range(d):
        seg_vol[:,:,i] = np.fliplr(np.transpose(seg_arr[i]))
    new_seg = nib.Nifti1Image(seg_vol, origin_volume.affine, origin_volume.header)
    nib.save(new_seg, os.path.join(output_dir, filename))

def split_filenames_train_val(IMG_PATH, val_prec=0.2, suffix='.png', is_sort=True):
    img_dir, _, filenams = next(os.walk(IMG_PATH))
    if suffix:
        filenams = [filename for filename in filenams if filename.endswith(suffix)]
    # masks_dir, _, _ = next(os.walk(MASK_PATH))
    if is_sort:
        filenams = sort_filenames(filenams)
        return split_to_val2(filenams, val_prec)
    else:
        return split_to_val(filenams, val_prec, shuffle=False)

def split_to_val(filenames, val_prec, shuffle=True):
    ''' split files name list into 2 groups (training and vlidtion according to
    val_prec: pecent of data for validation'''
    unique_indcies = get_unique_indices(filenames)
    num_val = int(len(unique_indcies) * val_prec)
    num_train = len(unique_indcies) - num_val
    train_indices = np.arange(num_train)
    # fix bug:
    # train_indices = unique_indcies
    val_indices = np.arange(num_train, num_train + num_val)

    if shuffle:
        # indices = np.random.permutation(len(filenams))
        np.random.shuffle(train_indices)
        np.random.shuffle(val_indices)

    train_filenames = []
    val_filenames = []
    patient_idx_all = split_and_get_idx_all(filenames, 0)
    for i, filename in enumerate(filenames):
        curr_patient = patient_idx_all[i]
        if curr_patient in unique_indcies[:num_train]:
            train_filenames.append(filename)
        else:
            val_filenames.append(filename)
    return train_filenames, val_filenames

def split_to_val2(filenames, val_prec):
    ''' split files name list into 2 groups (training and vlidtion according to
    val_prec: pecent of data for validation'''
    num_val = int(len(filenames) * val_prec)
    num_train = len(filenames) - num_val

    flatten = lambda l: [item for sorted_filenames in l for item in sorted_filenames]
    train_filenames = flatten(filenames[0:num_train])
    val_filenames = flatten(filenames[num_train:])
    return train_filenames, val_filenames

def sort_filenames(filenams):
    patient_indices_unique = get_unique_indices(filenams)

    sorted_filenames = []
    for patient_idx in patient_indices_unique:
        patient_list = get_specific_patient(filenams, 0, patient_idx)
        patient_indices = []
        sorted_slices = []
        for silcename in patient_list:
            patient_indices.append(int(silcename.split('_')[1][:-4]))
        sorted_indices=sorted(range(len(patient_indices)), key=lambda k: patient_indices[k])
        for sorted_idx in sorted_indices:
            sorted_slices.append(patient_list[sorted_idx])
        sorted_filenames.append(sorted_slices)

    return sorted_filenames

def get_unique_indices(filenams, idx=0):
    patient_indices = split_and_get_idx_all(filenams, idx)
    return list(set(patient_indices))

def split_and_get_idx_all(list, idx):
    val_list = []
    for val in list:
        val_list.append(int((val.split('_')[idx]).split('-')[1]))
    return val_list

def get_specific_patient(filenams, idx, patient_idx):
    patient_list = []
    for filename in filenams:
        curr_patient_idx = int((filename.split('_')[idx]).split('-')[1])
        if curr_patient_idx == patient_idx:
            patient_list.append(filename)
    return patient_list

def split_to_patients(filenames):
    patient_indices_unique = get_unique_indices(filenames)
    sorted_filenames = []
    for patient_idx in patient_indices_unique:
        patient_list = get_specific_patient(filenames, 0, patient_idx)
        sorted_filenames.append(patient_list)

    return (sorted_filenames)

"""Crop 3D"""
def get_CC_largerThanTh(arr, thresh=8000,dbg=False):
    if dbg:
        dbg_CC(arr, prec=0.02)

    print('Applying Connected Component and take components with num pixels > max_pixels')
    labels = label(arr)
    print('Found ', labels.max(), 'labels')
    max_label = 0
    # Find largestCC
    large_labels = []
    for c_label in range(1, labels.max()+1):
        curr_num_bins = np.sum(np.where(labels == c_label, 1, 0))
        print(c_label, ':', curr_num_bins)
        if curr_num_bins > thresh:
            large_labels.append(c_label)
    print('Max CC label is: ', max_label)

    print('Num liver before CC: ', np.sum(arr))
    is_first = True
    for c_label in large_labels:
        if is_first:
            arr = np.where(labels == c_label, 1, 0)
            is_first = False
        else:
            arr[labels == c_label] = 1
    print('Num liver After CC: ',np.sum(arr) )

    if dbg:
        dbg_CC(arr,prec=0.02)
    return arr

def dbg_CC(arr, prec=0.01):
    from mpl_toolkits.mplot3d import Axes3D
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    pos = np.where(arr == 1)
    num_points = int(np.round(prec * len(pos[0])))
    indices = np.random.permutation(len(pos[0]))[0:num_points]

    ax.scatter(pos[0][indices], pos[1][indices], pos[2][indices])
    ax.view_init(elev=230., azim=360)
    plt.show()
    plt.ioff()
    # plt.waitforbuttonpress()
    plt.close()

def get_crop_coordinates(img, pad_size=2):
    """ input: binaty @D image
        output: crop coordinates of minimal "1" area with gap padding"""
    im_h, im_w = img.shape
    liver_m, liver_n = np.where(img >= 1)
    h_min = min(liver_m) - pad_size
    h_max = max(liver_m) + pad_size
    h = h_max - h_min + 1
    w_min = min(liver_n) - pad_size
    w_max = max(liver_n) + pad_size
    w = w_max - w_min + 1
    gap = abs(h - w)
    pad_l = int(np.ceil(gap / 2.))
    pad_r = int(np.floor(gap / 2.))
    if h > w:
        w_min -= pad_l
        w_max += pad_r
        if w_min < 0:
            w_min = 0
            w_max += (0 - w_min)
        if w_max > im_w:
            w_min -= w_max - im_w
            w_max = im_w
    if h < w:
        h_min -= pad_l
        h_max += pad_r
        if h_min < 0:
            h_min = 0
            h_max += (0 - h_min)
        if h_max > im_h:
            h_min -= h_max - im_h
            h_max = im_h

    return h_min, h_max, w_min, w_max

def get_crop_coordinates_3D(img_arr, pad_size=1,dbg=False):
    """ input: binaty 3D image
        output: global crop coordinates of minimal "1" area with gap padding"""
    im_d, im_h, im_w = img_arr.shape
    liver_z, liver_h, liver_w = np.where(img_arr >= 1)
    h_min = min(liver_h) - pad_size
    h_max = max(liver_h) + pad_size
    h = h_max - h_min + 1
    w_min = min(liver_w) - pad_size
    w_max = max(liver_w) + pad_size
    w = w_max - w_min + 1
    gap = abs(h - w)
    pad_l = int(np.ceil(gap / 2.))
    pad_r = int(np.floor(gap / 2.))
    if h > w:
        w_min -= pad_l
        w_max += pad_r
        if w_min < 0:
            w_min = 0
            w_max += (0 - w_min)
        if w_max > im_w:
            w_min -= w_max - im_w
            w_max = im_w
    if h < w:
        h_min -= pad_l
        h_max += pad_r
        if h_min < 0:
            h_min = 0
            h_max += (0 - h_min)
        if h_max > im_h:
            h_min -= h_max - im_h
            h_max = im_h
    if dbg:
        from mpl_toolkits.mplot3d import Axes3D
        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')
        num_points = int(np.round(0.02 * len(liver_z)))
        indices = np.random.permutation(len(liver_z))[0:num_points]
        # ax.scatter(liver_h, liver_w, liver_z)
        ax.scatter(liver_h[indices], liver_w[indices],liver_z[indices],s=0.8)
        ax.plot([h_min,h_max,h_max,h_min,h_min],[w_min, w_min,w_max, w_max,w_min], zs=int(im_d / 2), zdir='z',color='black')
        ax.view_init(elev=180., azim=360)
        plt.show()
        plt.ioff()
        plt.waitforbuttonpress()
        plt.close()

    return h_min, h_max, w_min, w_max

# Polar, Cartesian processing
def centroid(img, lcc=False):
  if lcc:
    img = img.astype(np.uint8)
    nb_components, output, stats, centroids = cv2.connectedComponentsWithStats(img, connectivity=4)
    sizes = stats[:, -1]
    if len(sizes) > 2:
      max_label = 1
      max_size = sizes[1]

      for i in range(2, nb_components):
          if sizes[i] > max_size:
              max_label = i
              max_size = sizes[i]

      img2 = np.zeros(output.shape)
      img2[output == max_label] = 255
      img = img2

  if len(img.shape) > 2:
    M = cv2.moments(img[:,:,1])
  else:
    M = cv2.moments(img)

  if M["m00"] == 0:
    return (img.shape[0] // 2, img.shape[1] // 2)
  
  cX = int(M["m10"] / M["m00"])
  cY = int(M["m01"] / M["m00"])
  return (cX, cY)

def to_polar(input_img, center):
  #input_img = input_img.astype(np.float32)
  value = np.sqrt(((input_img.shape[0]/2.0)**2.0)+((input_img.shape[1]/2.0)**2.0))
  polar_image = cv2.linearPolar(input_img, center, value, cv2.WARP_FILL_OUTLIERS)
  polar_image = cv2.rotate(polar_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
  return polar_image

def to_cart(input_img, center):
  #input_img = input_img.astype(np.float32)
  input_img = cv2.rotate(input_img, cv2.ROTATE_90_CLOCKWISE)
  value = np.sqrt(((input_img.shape[1]/2.0)**2.0)+((input_img.shape[0]/2.0)**2.0))
  polar_image = cv2.linearPolar(input_img, center, value, cv2.WARP_FILL_OUTLIERS + cv2.WARP_INVERSE_MAP)
  #polar_image = polar_image.astype(np.uint8)
  return polar_image
