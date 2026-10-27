import os
from launch import LaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    # 定位功能包
    pkg_share = FindPackageShare(package='cartographer').find('cartographer')

    #配置节点启动信息
    use_sim_time = LaunchConfiguration('use_sim_time', default='false')
    # 地图的分辨率
    resolution = LaunchConfiguration('resolution', default='0.05')
    # 地图的发布周期
    publish_period_sec = LaunchConfiguration('publish_period_sec', default='1.0')
    # 配置文件夹路径
    configuration_directory = LaunchConfiguration('configuration_directory',default= os.path.join(pkg_share, 'config') )
    # 配置文件
    configuration_basename = LaunchConfiguration('configuration_basename', default='mapping_2d.lua')
    # 崩溃续扫：传入 autosave 的 .pbstream 路径，加载后继续建图
    load_state = LaunchConfiguration('load_state', default='')
    resuming = PythonExpression(["'", load_state, "' != ''"])

    base_args = ['-configuration_directory', configuration_directory,
                 '-configuration_basename', configuration_basename]

    #声明节点
    cartographer_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        condition=UnlessCondition(resuming),
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=base_args)

    # 续扫模式：加载上次的 pbstream 并以默认话题开启新轨迹
    cartographer_resume_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        condition=IfCondition(resuming),
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=base_args + ['-load_state_filename', load_state,
                               '-start_trajectory_with_default_topics'])

    cartographer_occupancy_grid_node = Node(
        package='cartographer_ros',
        executable='cartographer_occupancy_grid_node',
        name='cartographer_occupancy_grid_node',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=['-resolution', resolution, '-publish_period_sec', publish_period_sec])

    #启动文件
    ld = LaunchDescription()
    ld.add_action(cartographer_node)
    ld.add_action(cartographer_resume_node)
    ld.add_action(cartographer_occupancy_grid_node)

    return ld
