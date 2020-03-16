import cv2
import os
import numpy as np
import matplotlib.pyplot as plt
import json
import pandas as pd
import math
import yaml
from utils.calibration import Calibration

class Sequence:

    def __init__(self, sequence_path, config_file='config/config.yaml'):
        self.sequence_path = sequence_path
        
        self.annotations_path = os.path.join(
            self.sequence_path, 'annotations', 'annotations.json')
        self.load_annotations()

        with open(config_file, 'r') as file:
            self.config = yaml.full_load(file)

        self.calib = Calibration(self.config)
        
        self.colors = {'car': (1, 0, 0),
                       'bus': (0, 1, 0),
                       'truck': (0, 0, 1),
                       'pedestrian': (1.0, 1.0, 0.0),
                       'van': (1.0, 0.3, 0.0),
                       'group_of_pedestrians': (1.0, 1.0, 0.3),
                       'motorbike': (0.0, 1.0, 1.0),
                       'bicycle': (0.3, 1.0, 1.0)
                       }

        self.heights = {'car': 1.5,
                        'bus': 5,
                        'truck': 2.5,
                        'pedestrian': 1.8,
                        'van': 2,
                        'group_of_pedestrians': 1.8,
                        'motorbike': 1.5,
                        'bicycle': 1.5
                        }
    
        self.timestamp_camera = self.load_timestamp(os.path.join(self.sequence_path, self.config['camera_timestamp_file']))
        self.timestamp_radar = self.load_timestamp(os.path.join(self.sequence_path, self.config['radar_timestamp_file']))
        self.timestamp_lidar = self.load_timestamp(os.path.join(self.sequence_path, self.config['lidar_timestamp_file']))

        self.init_timestamp = np.min([self.timestamp_camera['time'][0],
                                     self.timestamp_lidar['time'][0],
                                     self.timestamp_radar['time'][0]])

        self.end_timestamp = np.max([self.timestamp_camera['time'][-1],
                                     self.timestamp_lidar['time'][-1],
                                     self.timestamp_radar['time'][-1]])

    def load_annotations(self):
        if (os.path.exists(self.annotations_path)):
            f = open(self.annotations_path)
            self.annotations = json.load(f)
        else:
            self.annotations = None

    def overlay_camera_lidar (self, camera, lidar):
        overlay = np.copy(camera)
        overlay[np.nonzero(lidar)] = lidar[np.nonzero(lidar)]
        return overlay

    def project_lidar(self, lidar, lidar_extrinsics, cam_intrinsic, color_mode='same'):
        fx = cam_intrinsic[0, 0]
        fy = cam_intrinsic[1, 1]
        cx = cam_intrinsic[0, 2]
        cy = cam_intrinsic[1, 2]
        if color_mode == 'same' or color_mode == 'pseudo_distance' :
            im_lidar = np.zeros((self.config['left_cam_calib']['res'][1],
                                 self.config['left_cam_calib']['res'][0], 3))
        else:
            im_lidar = np.zeros((self.config['left_cam_calib']['res'][1],
                                 self.config['left_cam_calib']['res'][0]))
        lidar_points = lidar[:, :3].T
        R = lidar_extrinsics[:3, :3]
        lidar_points = np.matmul(R, lidar_points).T
        lidar_points += lidar_extrinsics[:3, 3]
        for i in range(lidar.shape[0]):
            if (lidar_points[i, 2] > 0 and lidar_points[i, 2] < self.config['lidar_proj']['max_dist']):
                xx = int(((lidar_points[i, 0] * fx) / lidar_points[i, 2]) + cx)
                yy = int(((lidar_points[i, 1] * fy) / lidar_points[i, 2]) + cy)
                if (xx > 0 and xx < self.config['left_cam_calib']['res'][0] and
                 yy > 0 and yy < self.config['left_cam_calib']['res'][1]):
                    if color_mode == 'same':
                        im_lidar = cv2.circle(
                            im_lidar, (xx, yy), 1, color=(0, 255, 0))
                    elif color_mode == 'pseudo_distance':
                        dist = np.sqrt(lidar_points[i, 0]*lidar_points[i, 0] +
                               lidar_points[i, 1]*lidar_points[i, 1] +
                               lidar_points[i, 2]*lidar_points[i, 2])
                        norm_dist = np.array([(dist/self.config['lidar_proj']['max_dist'])*255]).astype(np.uint8)
                        # cc = cv2.applyColorMap(norm_dist,cv2.COLORMAP_JET)
                        cc = np.array(plt.get_cmap('viridis')(norm_dist))*255
                        im_lidar = cv2.circle(
                            im_lidar, (xx, yy), 1, color=cc.tolist()[0][:3][::-1])
                    elif color_mode == 'distance':
                        dist = np.sqrt(lidar_points[i, 0]*lidar_points[i, 0] +
                               lidar_points[i, 1]*lidar_points[i, 1] +
                               lidar_points[i, 2]*lidar_points[i, 2])
                        im_lidar[yy,xx] = distance

        return im_lidar

    def get_from_timestamp(self, t, get_sensors=True, get_annotations=True):
        id_camera = self.get_id(t, self.timestamp_camera, self.config['sync']['camera'])
        id_lidar = self.get_id(t, self.timestamp_lidar, self.config['sync']['lidar'])
        id_radar = self.get_id(t, self.timestamp_radar, self.config['sync']['radar'])
        output = {}
        if get_sensors :
            str_format = '{:06d}'

            # generata paths from frames
            im_left_path = os.path.join(
                self.sequence_path, 'zed_left', str_format.format(id_camera) + '.png')

            im_right_path = os.path.join(
                self.sequence_path, 'zed_right', str_format.format(id_camera) + '.png')

            radar_cartesian_path = os.path.join(
                self.sequence_path, 'Navtech_Cartesian', str_format.format(id_radar) + '.png')

            lidar_path = os.path.join(
                self.sequence_path, 'velo_lidar', str_format.format(id_lidar) + '.csv')

            sensors = {}
            if (self.config['use_camera_left_raw'] or
                self.config['use_camera_right_raw'] or
                self.config['use_camera_left_rect'] or
                self.config['use_camera_right_rect']) :
                im_left = cv2.imread(im_left_path)
                im_right = cv2.imread(im_right_path)

            if (self.config['use_camera_left_rect'] or self.config['use_camera_right_rect']):
                im_left_rect, im_right_rect, disp_to_depth = self.get_rectfied(im_left, im_right)

            if (self.config['use_lidar_pc'] or
                self.config['use_lidar_image'] or
                self.config['use_proj_lidar_left'] or
                self.config['use_proj_lidar_right']):
                lidar = self.read_lidar(lidar_path)
                

            if (self.config['use_camera_left_raw']):
                sensors['camera_left_raw'] = im_left

            if (self.config['use_camera_right_raw']):
                sensors['camera_right_raw'] = im_right

            if (self.config['use_camera_left_rect']):
                sensors['camera_left_rect'] = im_left_rect

            if (self.config['use_camera_right_rect']):
                sensors['camera_right_rect'] = im_right_rect

            if (self.config['use_radar_cartesian']):
                radar_cartesian = cv2.imread(radar_cartesian_path)
                sensors['radar_cartesian'] = radar_cartesian

            if (self.config['use_lidar_pc']):
                sensors['lidar_pc'] = lidar

            if (self.config['use_lidar_image']):
                sensors['lidar_image'] = self.lidar_to_image(lidar)

            if (self.config['use_proj_lidar_left']):
                proj_lidar_left = self.project_lidar(lidar, self.calib.LidarToLeft, self.calib.left_cam_mat,
                 color_mode=self.config['lidar_proj']['color_mode'])
                sensors['proj_lidar_left'] = proj_lidar_left

            if (self.config['use_proj_lidar_right']):
                proj_lidar_right = self.project_lidar(lidar, self.calib.LidarToRight, self.calib.right_cam_mat,
                    color_mode=self.config['lidar_proj']['color_mode'])
                sensors['proj_lidar_right'] = proj_lidar_right


            output['sensors'] = sensors

        if (get_annotations) :
            annotations = {}
            if (self.annotations != None):

                if self.config['use_radar_cartesian']:
                    radar_annotation_id = self.get_correct_radar_id_from_raw_ind(id_radar)
                    radar_annotations = self.get_annotation_from_id(radar_annotation_id)                
                    annotations['radar_cartesian'] = radar_annotations

                if self.config['use_lidar_image']:
                    annotations['lidar_image'] = self.get_lidar_annotations(id_radar)

                if self.config['use_camera_left_rect']:
                    annotations['lidar_image'] = self.get_lidar_annotations(id_radar)
                    bboxes_3d = self.project_bboxes_to_camera(annotations['lidar_image'],
                                             self.calib.left_cam_mat,
                                             self.calib.RadarToLeft)
                    annotations['camera_left_rect'] = bboxes_3d
                    

                if self.config['use_camera_right_rect']:
                    annotations['lidar_image'] = self.get_lidar_annotations(id_radar)
                    bboxes_3d = self.project_bboxes_to_camera(annotations['lidar_image'],
                                             self.calib.right_cam_mat,
                                             self.calib.RadarToRight)
                    annotations['camera_right_rect'] = bboxes_3d

            output['annotations'] = annotations
       
        return output

    def vis_all(self, output, wait_time=1):
# use_proj_lidar_left: True
# use_proj_lidar_right: True
        if self.config['use_camera_left_raw']:
            cv2.imshow('camera left raw', output['camera_left_raw'])

        if self.config['use_camera_right_raw']:
            cv2.imshow('camera right raw', output['camera_right_raw'])

        if self.config['use_camera_left_rect']:
            left_bb = self.vis_3d_bbox_cam(output['sensors']['camera_left_rect'], output['annotations']['camera_left_rect'])
            cv2.imshow('camera left', left_bb)

        if  self.config['use_camera_right_rect']:
            right_bb = self.vis_3d_bbox_cam(output['sensors']['camera_right_rect'], output['annotations']['camera_right_rect'])
            cv2.imshow('camera right', right_bb)

        if self.config['use_radar_cartesian']:
            radar_cart_vis = self.vis(output['sensors']['radar_cartesian'], output['annotations']['radar_cartesian'])
            cv2.imshow('radar', radar_cart_vis)

        if self.config['use_radar_polar']:
            cv2.imshow('radar', output['sensors']['radar_polar'])

        if (self.config['use_lidar_image']):
            lidar_vis = self.vis(output['sensors']['lidar_image'], output['annotations']['lidar_image'])
            cv2.imshow('lidar image', lidar_vis)
        
        if (self.config['use_lidar_pc']):
            pass

        if self.config['use_proj_lidar_left'] :
            overlay_left = self.overlay_camera_lidar(output['sensors']['camera_left_rect'],
                                                output['sensors']['proj_lidar_left'])
            overlay_left_bb = self.vis_3d_bbox_cam(overlay_left, output['annotations']['camera_left_rect'])
            cv2.imshow('projected lidar to left camera', overlay_left_bb)
        if self.config['use_proj_lidar_right'] :
            overlay_right = self.overlay_camera_lidar(output['sensors']['camera_right_rect'],
                                                output['sensors']['proj_lidar_right'])
            overlay_right_bb = self.vis_3d_bbox_cam(overlay_right, output['annotations']['camera_right_rect'])
            cv2.imshow('projected lidar to right camera', overlay_right_bb)

        
        cv2.waitKey(wait_time)
 

    def project_bboxes_to_camera(self, annotations, intrinsict, extrinsic):
        bboxes_3d = []
        for object in annotations:
            obj = {}
            class_name = object['class_name']
            obj['class_name'] = class_name
            obj['id'] = object['id']
            height = self.heights[class_name]
            bb = object['bbox']['position']
            rotation = object['bbox']['rotation']
            bbox_3d = self.get_projected_bbox(bb, rotation, intrinsict, extrinsic, height)
            obj['bbox_3d'] = bbox_3d
            bboxes_3d.append(obj)

        return bboxes_3d

    def vis_3d_bbox_cam(self, image, bboxes_3d):
        vis_im = np.copy(image)
        for obj in bboxes_3d:
            # bbox_3d = obj['bbox_3d']
            for ii in range(len(obj['bbox_3d'])):
                color = self.colors[obj['class_name']]
                vis_im = cv2.line(vis_im, (obj['bbox_3d'][ii - 1][0], obj['bbox_3d'][ii - 1][1]),
                          (obj['bbox_3d'][ii][0], obj['bbox_3d'][ii][1]), (np.array(color) * 255).astype(np.int).tolist(), 1)

        return vis_im
        

    def get_lidar_annotations(self, id_radar):
        lidar_annotation_id = self.get_correct_lidar_id_from_raw_ind(id_radar)
        lidar_annotations = self.get_annotation_from_id(lidar_annotation_id)
        M = self.calib.RadarToLidar

        h_width = self.config['lidar_image']['res'][0]/2.0
        h_height = self.config['lidar_image']['res'][1]/2.0
        cell_res_x = 100.0/h_width
        cell_res_y = 100.0/h_height
        
        # convert meters to pixel
        M[3,0] = M[3,0] / cell_res_x
        M[3,1] = M[3,1] / cell_res_y
        lidar_annotations = self.transform_annotations(lidar_annotations, M)                
        # annotations['lidar_image'] = lidar_annotations
        return lidar_annotations

    def get_rectfied(self, left_im, right_im):

        (leftRectification, rightRectification, leftProjection,
         rightProjection, dispartityToDepthMap, leftROI, rightROI) = cv2.stereoRectify(
            cameraMatrix1=self.calib.left_cam_mat,
            distCoeffs1=self.calib.left_cam_dist,
            cameraMatrix2=self.calib.right_cam_mat,
            distCoeffs2=self.calib.right_cam_dist,
            imageSize=tuple(self.calib.left_cam_res),
            R=self.calib.stereoR,
            T=self.calib.stereoT,
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0
        )

        leftMapX, leftMapY = cv2.initUndistortRectifyMap(
            self.calib.left_cam_mat,
            self.calib.left_cam_dist,
            leftRectification,
            leftProjection, tuple(self.calib.left_cam_res), cv2.CV_32FC1)

        rightMapX, rightMapY = cv2.initUndistortRectifyMap(
            self.calib.right_cam_mat,
            self.calib.left_cam_dist,
            rightRectification,
            rightProjection, tuple(self.calib.left_cam_res), cv2.CV_32FC1)

        fixedLeft = cv2.remap(left_im, leftMapX,
                              leftMapY, cv2.INTER_LINEAR)
        fixedRight = cv2.remap(right_im, rightMapX,
                               rightMapY, cv2.INTER_LINEAR)

        return fixedLeft, fixedRight, dispartityToDepthMap

    def transform_annotations (self, annotations, M):
        new_annotations = []
        for object in annotations:
            new_object = object
            xx = object['bbox']['position'][0]
            yy = object['bbox']['position'][1]
            zz = self.config['sensors_height']
            pos = np.array([xx, yy, zz, 1])
            new_pos = np.matmul(M, pos)
            new_pos = new_pos/new_pos[3]
            new_object['bbox']['position'][0] = pos[0]
            new_object['bbox']['position'][1] = pos[1]
            new_annotations.append(new_object)
        return new_annotations

    def get_annotation_from_id(self, annotation_id):
        raw_annotations = []
        for object in self.annotations:
            if (object['bboxes'][annotation_id]):
                obj = {}
                obj['id'] = object['id']
                obj['class_name'] = object['class_name']
                obj['bbox'] = object['bboxes'][annotation_id]
                raw_annotations.append(obj)
        return raw_annotations

    def inner_lidar_image(self, lidar,
                                image,
                                i,
                                cell_res_x,
                                cell_res_y,
                                h_width,
                                h_height) :
        xyzi = lidar[i]
        x = xyzi[0]/cell_res_x + h_width
        y = h_height - xyzi[1]/cell_res_y
        if self.config['lidar_image']['use_ring']:
            c = int(xyzi[4]) * 8
        else:
            c = int(xyzi[3])
        image = cv2.circle(image, (int(x),int(y)), 1, (c,c,c))
        return image


    def lidar_to_image(self, lidar):
        image = np.zeros((self.config['lidar_image']['res'][0], self.config['lidar_image']['res'][1], 3))
        h_width = self.config['lidar_image']['res'][0]/2.0
        h_height = self.config['lidar_image']['res'][1]/2.0
        cell_res_x = 100.0/h_width
        cell_res_y = 100.0/h_height
        for i in range(lidar.shape[0]):
            if self.config['lidar_image']['remove_ground']:
                if lidar[i,2] > -self.config['lidar_image']['ground_thresh'] :
                    image = self.inner_lidar_image(lidar, image, i, cell_res_x, cell_res_y, h_width, h_height)
            else:
                image = self.inner_lidar_image(lidar, image, i, cell_res_x, cell_res_y, h_width, h_height)
        return image.astype(np.uint8)

    def get_correct_radar_id_from_raw_ind(self, id):
        return id-1

    def get_correct_lidar_id_from_raw_ind(self, id):
        return id-1

    def vis (self, sensor, annotations):
        sensor_vis = np.copy(sensor)
        for object in annotations:
            bbox = object['bbox']['position']
            angle = object['bbox']['rotation']
        
            class_name = object['class_name']
            color = self.colors[class_name]
            sensor_vis = self.draw_boundingbox_rot(
                sensor_vis, bbox, angle, color)

        return sensor_vis

        

    def read_lidar(self, lidar_path):
        return pd.read_csv(lidar_path, delimiter=',').values

    def get_id(self, t, all_timestamps, time_offset=0.0):
        return all_timestamps['frame'][np.argmin(np.abs(all_timestamps['time'] - t + time_offset))]

    def load_timestamp(self, timestamp_path):
        genfromtxt = np.genfromtxt(
            timestamp_path, dtype=(str, int, str, float))
        timestamps = {'frame': [], 'time': []}
        for line in genfromtxt:
            timestamps['frame'].append(line[1])
            timestamps['time'].append(line[3])
        return timestamps

    

    def get_projected_bbox(self, bb, rotation, cameraMatrix, extrinsic, obj_height=2):
        rotation = np.deg2rad(-rotation)
        res = self.config['radar_calib']['range_res']
        cx = bb[0] + bb[2] / 2
        cy = bb[1] + bb[3] / 2
        T = np.array([[cx], [cy]])
        pc = 0.2
        bb = [bb[0]+bb[2]*pc, bb[1]+bb[3]*pc, bb[2]-bb[2]*pc, bb[3]-bb[3]*pc]

        R = np.array([[np.cos(rotation), -np.sin(rotation)],
                      [np.sin(rotation), np.cos(rotation)]])

        points = np.array([[bb[0], bb[1]],
                           [bb[0] + bb[2], bb[1]],
                           [bb[0] + bb[2], bb[1] + bb[3]],
                           [bb[0], bb[1] + bb[3]],
                           [bb[0], bb[1]],
                           [bb[0] + bb[2], bb[1] + bb[3]]]).T

        points = points - T
        points = np.matmul(R, points) + T
        points = points.T

        points[:, 0] = points[:, 0] - self.config['radar_calib']['range_cells']
        points[:, 1] = self.config['radar_calib']['range_cells'] - points[:, 1]
        points = points * res

        points = np.append(points, np.ones(
            (points.shape[0], 1)) * -1.7, axis=1)
        p1 = points[0, :]
        p2 = points[1, :]
        p3 = points[2, :]
        p4 = points[3, :]

        p5 = np.array([p1[0], p1[1], p1[2] + obj_height])
        p6 = np.array([p2[0], p2[1], p2[2] + obj_height])
        p7 = np.array([p3[0], p3[1], p3[2] + obj_height])
        p8 = np.array([p4[0], p4[1], p4[2] + obj_height])
        points = np.array([p1, p2, p3, p4, p1, p5, p6, p2, p6,
                           p7, p3, p7, p8, p4, p8, p5, p4, p3, p2, p6, p3])

        # translation
        points[:, 0] = points[:, 0]
        points[:, 1] = points[:, 1]

        points = np.matmul(np.append(points, np.ones(
            (points.shape[0], 1)), axis=1), extrinsic.T)

        points = (points / points[:, 3, None])[:, 0:3]

        filtered_indices = []
        for i in range(points.shape[0]):
            if (points[i, 2] > 0 and points[i, 2] < self.config['max_range_bbox_camera']):
                filtered_indices.append(i)

        points = points[filtered_indices]

        fx = cameraMatrix[0, 0]
        fy = cameraMatrix[1, 1]
        cx = cameraMatrix[0, 2]
        cy = cameraMatrix[1, 2]

        xIm = np.round((fx * points[:, 0] / points[:, 2]) + cx).astype(np.int)
        yIm = np.round((fy * points[:, 1] / points[:, 2]) + cy).astype(np.int)

        proj_bbox_3d = []
        for ii in range(1, xIm.shape[0]):
            proj_bbox_3d.append([xIm[ii], yIm[ii]])
        proj_bbox_3d = np.array(proj_bbox_3d)

        # for ii in range(1, xIm.shape[0]):
        #     im = cv2.line(im, (xIm[ii - 1], yIm[ii - 1]),
        #                   (xIm[ii], yIm[ii]), (np.array(color) * 255).astype(np.int).tolist(), 1)
        # plt.plot(xIm, yIm)
        #             text(xIm(1), yIm(1), strrep(class, '_', '-'), 'Color', color, 'FontWeight', 'bold')

        return proj_bbox_3d

    def draw_boundingbox_rot(self, im, bbox, angle, color):
        theta = np.deg2rad(-angle)
        R = np.array([[np.cos(theta), -np.sin(theta)],
                      [np.sin(theta), np.cos(theta)]])
        points = np.array([[bbox[0], bbox[1]],
                           [bbox[0] + bbox[2], bbox[1]],
                           [bbox[0] + bbox[2], bbox[1] + bbox[3]],
                           [bbox[0], bbox[1] + bbox[3]]]).T

        cx = bbox[0] + bbox[2] / 2
        cy = bbox[1] + bbox[3] / 2
        T = np.array([[cx], [cy]])

        points = points - T
        points = np.matmul(R, points) + T
        points = points.astype(int)

        # color = (255, 0, 0)
        color = (np.array(color) * 255).tolist()

        cv2.line(im, tuple(points[:, 0]), tuple(points[:, 1]), color, 3)
        cv2.line(im, tuple(points[:, 1]), tuple(points[:, 2]), color, 3)
        cv2.line(im, tuple(points[:, 2]), tuple(points[:, 3]), color, 3)
        cv2.line(im, tuple(points[:, 3]), tuple(points[:, 0]), color, 3)

        return im


    def linear_interpolation(self, p1,t_c, t_r1, t_r2, p2):
        return p1 + (t_c - t_r1)*((p2 - p1)/(t_r2 - t_r1))

    def draw_bboxes_camera(self, i, im, cameraMatrix1, leftExtrinsic,offset=1):
        if (self.annotations != None):
            for object in self.annotations:
                if self.object_exist(object,i, offset):
                    bbox = object['bboxes'][i+offset]['position']
                    angle = object['bboxes'][i+offset]['rotation']
                    if self.object_exist(object, i+1, offset):
                        bbox2 = object['bboxes'][i+offset+1]['position']
                        t_c = self.timestamps_left_im['time'][int(self.im_ids[int(self.radar_ids[i+offset])])]
                        t_r1 = self.timestamps_radar['time'][int(self.radar_ids[i+offset])]
                        t_r2 = self.timestamps_radar['time'][int(self.radar_ids[i+offset+1])]
                        px1 = bbox[0]
                        px2 = bbox2[0]
                        py1 = bbox[1]
                        py2 = bbox2[1]
                        npx = self.linear_interpolation(px1, t_c, t_r1, t_r2, px2)
                        npy = self.linear_interpolation(py1, t_c, t_r1, t_r2, py2)
                        bbox[0] = npx
                        bbox[1] = npy
                        # diff_ts = im_ts_curr - radar_ts_curr
                        # y = y1 + (x - x1) *((y2 - y1)/(x2 - x1))



                    #color = object['color']
                    class_name = object['class_name']
                    color = self.colors[class_name]
                    # radar_cartesian = self.draw_boundingbox_rot(
                    #     radar_cartesian, bbox, angle, color)
                    # if (project_bboxes):
                    height = self.heights[class_name]
                    im = self.drawProjectedBBoxes(
                        im, bbox, angle, color, cameraMatrix1, leftExtrinsic, height)
        return im

        # def get_frame_ids(self, timestamps_radar,
    #                   timestamps_left_im,
    #                   timestamps_lidar):
    #     self.total_nb_frames_radar = len(timestamps_radar['frame'])

    #     im_ids = np.zeros((self.total_nb_frames_radar))
    #     lidar_ids = np.zeros((self.total_nb_frames_radar))
    #     radar_ids = np.zeros((self.total_nb_frames_radar))
    #     time = timestamps_radar['time']

    #     # get the ids from radar ids
    #     for i in range(self.total_nb_frames_radar):
    #         im_ids[i] = self.get_id(time[i], timestamps_left_im['time'])
    #         lidar_ids[i] = self.get_id(time[i], timestamps_lidar['time'])
    #         radar_ids[i] = i + 1
    #     return im_ids, lidar_ids, radar_ids




        # self.load_sequence()
        # self.load_annotations()

    # def drawLidar(self):
    #     pass

    # def drawRadarLidar(self):
    #     pass

    # def addText(self, im, pos, text, size):
    #     cv2.putText(
    #         im, text, pos, cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), 3)  # font stroke

    # def get_annotation(self):
    #     return self.annotations

    # def get_sensors_from_frame(self, frame, offset_im=-1, offset_lidar=-1):
    #     # get correct frames
    #     radar_id = int(self.radar_ids[frame])

    #     im_left_id = int(self.im_ids[frame+offset_im])
    #     lidar_id = int(self.lidar_ids[frame+offset_lidar])

    #     str_format = '{:06d}'

    #     # generata paths from frames
    #     im_left_path = os.path.join(
    #         self.sequence_path, 'zed_left', str_format.format(im_left_id) + '.png')

    #     im_right_path = os.path.join(
    #         self.sequence_path, 'zed_right', str_format.format(im_left_id) + '.png')

    #     radar_cartesian_path = os.path.join(
    #         self.sequence_path, 'Navtech_Cartesian', str_format.format(radar_id) + '.png')

    #     lidar_path = os.path.join(
    #         self.sequence_path, 'velo_lidar', str_format.format(lidar_id) + '.csv')

    #     # read sensors
    #     im_left = cv2.imread(im_left_path)
    #     im_right = cv2.imread(im_right_path)
    #     lidar = self.read_lidar(lidar_path)
    #     radar_cartesian = cv2.imread(radar_cartesian_path)

    #     return im_left, im_right, lidar, radar_cartesian

    # def drawLegend(self, im, size=3):
    #     pos = (50, 50)
    #     for class_name in colors:
    #         color = colors[class_name]
    #         color = (color[0] * 255, color[1] * 255, color[2]*255)
    #         cv2.rectangle(im, (pos[0] - 40, pos[1]-30),
    #                       (pos[0]-10, pos[1]), color, thickness=-1)
    #         self.addText(im, pos, class_name, size)

    #         pos = (pos[0], pos[1] + 60)

    # def draw_radar_lidar(self, radar, lidar_image):
    #     radar_bin = radar > 65
    #     return (radar_bin*255 + lidar_image).astype(np.uint8)

    # def draw_bboxes_bev(self, i, radar, extrinsic=np.eye(4), offset=0, interpolate=False):
    #     if (self.annotations != None):
    #         for object in self.annotations:
    #             if (object['bboxes'][i]):
    #                 if (object['deleted'][i] == 0):
    #                     if (object['visible'][i] == 'visible'):
    #                         bbox = object['bboxes'][i+offset]['position']
    #                         if interpolate:
    #                             if self.object_exist(object, i+1, offset):
    #                                 bbox2 = object['bboxes'][i+offset+1]['position']
    #                                 t_l = self.timestamps_lidar['time'][int(self.lidar_ids[int(self.radar_ids[i+offset])])]
    #                                 t_r1 = self.timestamps_radar['time'][int(self.radar_ids[i+offset])]
    #                                 t_r2 = self.timestamps_radar['time'][int(self.radar_ids[i+offset+1])]
    #                                 px1 = bbox[0]
    #                                 px2 = bbox2[0]
    #                                 py1 = bbox[1]
    #                                 py2 = bbox2[1]
    #                                 npx = self.linear_interpolation(px1, t_l, t_r1, t_r2, px2)
    #                                 npy = self.linear_interpolation(py1, t_l, t_r1, t_r2, py2)
    #                                 bbox[0] = npx
    #                                 bbox[1] = npy
    #                         bbox[0] += extrinsic[3,0]
    #                         bbox[1] += extrinsic[3,1]
    #                         angle = object['bboxes'][i]['rotation']
    #                         #color = object['color']
    #                         class_name = object['class_name']
    #                         color = self.colors[class_name]
    #                         radar = self.draw_boundingbox_rot(
    #                             radar, bbox, angle, color)
    #     return radar

    # def lidarToImage(self, lidar):
    #     image = np.zeros((1152, 1152,3 ))
    #     for i in range(lidar.shape[0]):
    #         #if lidar[i,2] > -1.5 :
    #             xyzi = lidar[i]
    #             x = xyzi[0]/0.173611 + 576
    #             y = 576 - xyzi[1]/0.173611
    #             c = int(xyzi[4])
    #             image = cv2.circle(image, (int(x),int(y)), 1, (0,c,0))
    #     return image.astype(np.uint8)*8


    # def drawProjectedLidar(self, im, lidar, cameraParams, lidarExtrinsics, color_mode='same'):
    #     fx = cameraParams[0, 0]
    #     fy = cameraParams[1, 1]
    #     cx = cameraParams[0, 2]
    #     cy = cameraParams[1, 2]
    #     im_lidar = im.copy()
    #     lidar_points = lidar[:, :3].T
    #     R = lidarExtrinsics[:3, :3]
    #     lidar_points = np.matmul(R, lidar_points).T
    #     lidar_points += lidarExtrinsics[:3, 3]
    #     for i in range(lidar.shape[0]):
    #         if (lidar_points[i, 2] > 0 and lidar_points[i, 2] < 50):# and lidar_points[i,1] > -2):
    #             xx = int(((lidar_points[i, 0] * fx) / lidar_points[i, 2]) + cx)
    #             yy = int(((lidar_points[i, 1] * fy) / lidar_points[i, 2]) + cy)
    #             if (xx > 0 and xx < im.shape[1] and yy > 0 and yy < im.shape[0]):
    #                 if color_mode == 'same':
    #                     im_lidar = cv2.circle(
    #                         im_lidar, (xx, yy), 1, color=(0, 255, 0))
    #                 else:
    #                     dist = np.sqrt(lidar_points[i, 0]*lidar_points[i, 0] +
    #                            lidar_points[i, 1]*lidar_points[i, 1] +
    #                            lidar_points[i, 2]*lidar_points[i, 2])
    #                     norm_dist = np.array([(dist/50)*255]).astype(np.uint8)
    #                     # cc = cv2.applyColorMap(norm_dist,cv2.COLORMAP_JET)
    #                     cc = np.array(plt.get_cmap('viridis')(norm_dist))*255
    #                     im_lidar = cv2.circle(
    #                         im_lidar, (xx, yy), 1, color=cc.tolist()[0][:3][::-1])
    #     return im_lidar

    # def drawProjectedBBoxes(self, im, bb, rotation, color, cameraMatrix, extrinsic, obj_height=2):
    #     rotation = np.deg2rad(-rotation)
    #     res = 0.1736111
    #     cx = bb[0] + bb[2] / 2
    #     cy = bb[1] + bb[3] / 2
    #     T = np.array([[cx], [cy]])
    #     pc = 0.2
    #     bb = [bb[0]+bb[2]*pc, bb[1]+bb[3]*pc, bb[2]-bb[2]*pc, bb[3]-bb[3]*pc]

    #     R = np.array([[np.cos(rotation), -np.sin(rotation)],
    #                   [np.sin(rotation), np.cos(rotation)]])

    #     points = np.array([[bb[0], bb[1]],
    #                        [bb[0] + bb[2], bb[1]],
    #                        [bb[0] + bb[2], bb[1] + bb[3]],
    #                        [bb[0], bb[1] + bb[3]],
    #                        [bb[0], bb[1]],
    #                        [bb[0] + bb[2], bb[1] + bb[3]]]).T

    #     points = points - T
    #     points = np.matmul(R, points) + T
    #     points = points.T

    #     points[:, 0] = points[:, 0] - 576
    #     points[:, 1] = 576 - points[:, 1]
    #     points = points * res

    #     points = np.append(points, np.ones(
    #         (points.shape[0], 1)) * -1.7, axis=1)
    #     p1 = points[0, :]
    #     p2 = points[1, :]
    #     p3 = points[2, :]
    #     p4 = points[3, :]

    #     p5 = np.array([p1[0], p1[1], p1[2] + obj_height])
    #     p6 = np.array([p2[0], p2[1], p2[2] + obj_height])
    #     p7 = np.array([p3[0], p3[1], p3[2] + obj_height])
    #     p8 = np.array([p4[0], p4[1], p4[2] + obj_height])
    #     points = np.array([p1, p2, p3, p4, p1, p5, p6, p2, p6,
    #                        p7, p3, p7, p8, p4, p8, p5, p4, p3, p2, p6, p3])

    #     # translation
    #     points[:, 0] = points[:, 0] - 0.1
    #     points[:, 1] = points[:, 1] - 0.5

    #     points = np.matmul(np.append(points, np.ones(
    #         (points.shape[0], 1)), axis=1), extrinsic.T)

    #     points = (points / points[:, 3, None])[:, 0:3]

    #     filtered_indices = []
    #     for i in range(points.shape[0]):
    #         if (points[i, 2] > 0 and points[i, 2] < 50):
    #             filtered_indices.append(i)

    #     points = points[filtered_indices]

    #     fx = cameraMatrix[0, 0]
    #     fy = cameraMatrix[1, 1]
    #     cx = cameraMatrix[0, 2]
    #     cy = cameraMatrix[1, 2]

    #     xIm = np.round((fx * points[:, 0] / points[:, 2]) + cx).astype(np.int)
    #     yIm = np.round((fy * points[:, 1] / points[:, 2]) + cy).astype(np.int)

    #     for ii in range(1, xIm.shape[0]):
    #         im = cv2.line(im, (xIm[ii - 1], yIm[ii - 1]),
    #                       (xIm[ii], yIm[ii]), (np.array(color) * 255).astype(np.int).tolist(), 1)
    #     # plt.plot(xIm, yIm)
    #     #             text(xIm(1), yIm(1), strrep(class, '_', '-'), 'Color', color, 'FontWeight', 'bold')

    #     return im

    # def draw_boundingbox_rot(self, im, bbox, angle, color):
    #     theta = np.deg2rad(-angle)
    #     R = np.array([[np.cos(theta), -np.sin(theta)],
    #                   [np.sin(theta), np.cos(theta)]])
    #     points = np.array([[bbox[0], bbox[1]],
    #                        [bbox[0] + bbox[2], bbox[1]],
    #                        [bbox[0] + bbox[2], bbox[1] + bbox[3]],
    #                        [bbox[0], bbox[1] + bbox[3]]]).T

    #     cx = bbox[0] + bbox[2] / 2
    #     cy = bbox[1] + bbox[3] / 2
    #     T = np.array([[cx], [cy]])

    #     points = points - T
    #     points = np.matmul(R, points) + T
    #     points = points.astype(int)

    #     # color = (255, 0, 0)
    #     color = (np.array(color) * 255).tolist()

    #     cv2.line(im, tuple(points[:, 0]), tuple(points[:, 1]), color, 3)
    #     cv2.line(im, tuple(points[:, 1]), tuple(points[:, 2]), color, 3)
    #     cv2.line(im, tuple(points[:, 2]), tuple(points[:, 3]), color, 3)
    #     cv2.line(im, tuple(points[:, 3]), tuple(points[:, 0]), color, 3)

    #     return im

    # def load_annotations(self):
    #     if (os.path.exists(self.annotation_path)):
    #         f = open(self.annotation_path)
    #         self.annotations = json.load(f)
    #     else:
    #         self.annotations = None

    # def object_exist(self, object, i, offset):
    #     if (object['bboxes'][i+offset]):
    #         if (object['deleted'][i+offset] == 0):
    #             if (object['visible'][i+offset] == 'visible'):
    #                 return True
    #     return False

    # def linear_interpolation(self, p1,t_c, t_r1, t_r2, p2):
    #     return p1 + (t_c - t_r1)*((p2 - p1)/(t_r2 - t_r1))

    # def draw_bboxes_camera(self, i, im, cameraMatrix1, leftExtrinsic,offset=1):
    #     if (self.annotations != None):
    #         for object in self.annotations:
    #             if self.object_exist(object,i, offset):
    #                 bbox = object['bboxes'][i+offset]['position']
    #                 angle = object['bboxes'][i+offset]['rotation']
    #                 if self.object_exist(object, i+1, offset):
    #                     bbox2 = object['bboxes'][i+offset+1]['position']
    #                     t_c = self.timestamps_left_im['time'][int(self.im_ids[int(self.radar_ids[i+offset])])]
    #                     t_r1 = self.timestamps_radar['time'][int(self.radar_ids[i+offset])]
    #                     t_r2 = self.timestamps_radar['time'][int(self.radar_ids[i+offset+1])]
    #                     px1 = bbox[0]
    #                     px2 = bbox2[0]
    #                     py1 = bbox[1]
    #                     py2 = bbox2[1]
    #                     npx = self.linear_interpolation(px1, t_c, t_r1, t_r2, px2)
    #                     npy = self.linear_interpolation(py1, t_c, t_r1, t_r2, py2)
    #                     bbox[0] = npx
    #                     bbox[1] = npy
    #                     # diff_ts = im_ts_curr - radar_ts_curr
    #                     # y = y1 + (x - x1) *((y2 - y1)/(x2 - x1))



    #                 #color = object['color']
    #                 class_name = object['class_name']
    #                 color = self.colors[class_name]
    #                 # radar_cartesian = self.draw_boundingbox_rot(
    #                 #     radar_cartesian, bbox, angle, color)
    #                 # if (project_bboxes):
    #                 height = self.heights[class_name]
    #                 im = self.drawProjectedBBoxes(
    #                     im, bbox, angle, color, cameraMatrix1, leftExtrinsic, height)
    #     return im

    # def load_timestamp(self, timestamp_path):
    #     genfromtxt = np.genfromtxt(
    #         timestamp_path, dtype=(str, int, str, float))
    #     timestamps = {'frame': [], 'time': []}
    #     for line in genfromtxt:
    #         timestamps['frame'].append(line[1])
    #         timestamps['time'].append(line[3])
    #     return timestamps

    # def get_id(self, unique_time_sensor1, times_sensor2):
    #     return np.argmin(np.abs(times_sensor2 - unique_time_sensor1)) + 1

    # # get the ids from radar ids
    # def get_frame_ids(self, timestamps_radar,
    #                   timestamps_left_im,
    #                   timestamps_lidar):
    #     self.total_nb_frames_radar = len(timestamps_radar['frame'])

    #     im_ids = np.zeros((self.total_nb_frames_radar))
    #     lidar_ids = np.zeros((self.total_nb_frames_radar))
    #     radar_ids = np.zeros((self.total_nb_frames_radar))
    #     time = timestamps_radar['time']

    #     # get the ids from radar ids
    #     for i in range(self.total_nb_frames_radar):
    #         im_ids[i] = self.get_id(time[i], timestamps_left_im['time'])
    #         lidar_ids[i] = self.get_id(time[i], timestamps_lidar['time'])
    #         radar_ids[i] = i + 1
    #     return im_ids, lidar_ids, radar_ids

    # def read_lidar(self, lidar_path):
    #     return pd.read_csv(lidar_path, delimiter=',').values

    # def draw_radar_and_camera(self, radar, camera, mode='hor'):
    #     try:
    #         if mode == 'hor':
    #             im = np.zeros(
    #                 (radar.shape[0], radar.shape[1] + camera.shape[1], 3))

    #             im[:, camera.shape[1]:, :] = radar
    #             im[math.floor(radar.shape[0] / 2 - camera.shape[0] / 2): math.floor(
    #                 radar.shape[0] / 2 + camera.shape[0] / 2), : camera.shape[1], :] = camera
    #         else:
    #             im = np.zeros(
    #                 (radar.shape[0] + camera.shape[0], radar.shape[1], 3))

    #             im[camera.shape[0]:, :, :] = radar
    #             im[:camera.shape[0], math.floor(radar.shape[1] / 2 - camera.shape[1] / 2): math.floor(
    #                 radar.shape[1] / 2 + camera.shape[1] / 2), :] = camera
    #     except:
    #         camera = np.zeros((380, 825, 3))
    #         im = self.draw_radar_and_camera(radar, camera, mode)
    #     return im.astype(np.uint8)

    # def load_sequence(self):
    #     # get all time stamps
    #     timestamps_left_path = os.path.join(self.sequence_path, 'zed_left.txt')
    #     timestamps_radar_path = os.path.join(
    #         self.sequence_path, 'Navtech_Cartesian.txt')
    #     timestamps_lidar_path = os.path.join(
    #         self.sequence_path, 'velo_lidar.txt')

    #     self.timestamps_left_im = self.load_timestamp(timestamps_left_path)
    #     self.timestamps_radar = self.load_timestamp(timestamps_radar_path)
    #     self.timestamps_lidar = self.load_timestamp(timestamps_lidar_path)

    #     self.im_ids, self.lidar_ids, self.radar_ids = self.get_frame_ids(self.timestamps_radar,
    #                                                       self.timestamps_left_im,
    #                                                       self.timestamps_lidar)
    #     self.total_nb_frames_radar = len(self.timestamps_radar['frame'])

