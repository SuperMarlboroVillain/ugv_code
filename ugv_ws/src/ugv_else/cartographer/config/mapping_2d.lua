include "map_builder.lua"  
include "trajectory_builder.lua"  

options = {
  map_builder = MAP_BUILDER,  
  trajectory_builder = TRAJECTORY_BUILDER,  
  map_frame = "map",  -- 地图帧的名称
  tracking_frame = "base_footprint",  -- 跟踪帧的名称
  published_frame = "odom",  -- 发布帧的名称
  odom_frame = "odom",  -- 里程计帧的名称
  provide_odom_frame = false,  -- 是否提供里程计帧
  publish_frame_projected_to_2d = false,  -- 是否发布2d姿态
  use_pose_extrapolator = false,
  use_odometry = true,  -- 是否使用里程计
  use_nav_sat = false,  -- 是否使用导航卫星
  use_landmarks = false,  -- 是否使用地标
  num_laser_scans = 1,  -- 激光雷达的数量
  num_multi_echo_laser_scans = 0,  -- 多回波激光雷达的数量
  num_subdivisions_per_laser_scan = 1,  -- 每个激光扫描的细分数量
  num_point_clouds = 0,  -- 点云的数量
  lookup_transform_timeout_sec = 0.2,  -- 查找变换的超时时间（秒）
  submap_publish_period_sec = 0.3,  -- 子地图发布周期（秒）
  pose_publish_period_sec = 5e-3,  -- 姿态发布周期（秒）
  trajectory_publish_period_sec = 30e-3,  -- 轨迹发布周期（秒）
  rangefinder_sampling_ratio = 1.,  -- 测距仪采样比率
  odometry_sampling_ratio = 1.,  -- 里程计采样比率
  fixed_frame_pose_sampling_ratio = 1.,  -- 固定帧姿态采样比率
  imu_sampling_ratio = 1.,  -- IMU采样比率
  landmarks_sampling_ratio = 1.,  -- 地标采样比率
}
 
MAP_BUILDER.use_trajectory_builder_2d = true  -- 是否启动2D SLAM
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 35  -- 2D轨迹构建器中子地图的范围数据数量
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.hit_probability = 0.60  -- 默认0.55,墙线更快实化,重影更少
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.miss_probability = 0.47  -- 默认0.49,杂点/鬼影更快被清除
TRAJECTORY_BUILDER_2D.min_range = 0.05  -- LD19 近端量程，贴近车身的低矮障碍也能进图
TRAJECTORY_BUILDER_2D.max_range = 8.0  -- LD19 有效量程约 8~12m；3.5m 会把远处障碍整片漏掉
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 3.5  -- 8.改成3.5,无回波射线只画3.5m,消除房间外"太阳光芒";远处墙线由真实命中绘制不受影响
TRAJECTORY_BUILDER_2D.use_imu_data = false  -- 是否使用IMU数据
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = false  -- true改成false,每次扫描的全相关匹配是CPU大头;有里程计+ceres匹配足够,降低死机风险
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.1
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(10.)  -- 默认20°,预收窄到10°:万一重开在线匹配,CPU开销减半

TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(0.5)  -- 0.1改成0.5:0.1°低于轮式里程计噪声地板,静止时也近10Hz插scan(冒烟实测静止插入174帧);0.5°仍是默认值的5倍敏感度
POSE_GRAPH.constraint_builder.min_score = 0.65  -- 0.55改成0.65,Fast csm的最低分数，高于此分数才进行优化。
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.7  --0.6改成0.7,全局定位最小分数，低于此分数则认为目前全局定位不准确

return options
