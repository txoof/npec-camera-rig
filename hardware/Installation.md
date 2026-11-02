# Daylight Growth Chamber Hardware Installation Instructions <!-- omit in toc -->

- [Conventions](#conventions)
- [Raspberry Pi 5 Preparation](#raspberry-pi-5-preparation)
- [Camera Mount Installation](#camera-mount-installation)
- [Calibration and Setup](#calibration-and-setup)

## Conventions

Standing in the chamber door way, with the control panel to the right, the following conventions are used to define the chamber layout.

- Left side: West
- Right side: East
- Front (closest to door): South
- Back (farthest from door): North

When using this camera system, a maximum of 12 trays can be effectively captured. Trays are expected to be placed in two rows of six each. With the long edge oriented north/south. Other orientations are possible and should work, but the area around the drain cannot be effectively used and should be excluded.

**Top View**

```text
     NW                    North            NE
     ┌───────────────────────────────────────┐
     │ D                                     │
     │ R                   │                 │
West │ A ────────equator───+──equator─────── │ East
     │ I                   │                 │
     │ N                                     │
     └───────────────────────────────────────┘
     SW                   South             SE


    │
> ──+── < Geographic center of the table excluding the drain width
    │

```

**Front View**

```text
                    Top Support
    ┌───────────────────────────────────────┐
    │                                       │
    │                                       │
    │                                       │
    │                                       │
    ├───────────────────────────────────────┤
    │                 Table                 │
    ├───────────────────────────────────────┤
    │                                       │
    │                                       │
    │                                       │
```

## [Raspberry Pi 5 Preparation](#raspberry-pi-5-preparation)

This section prepares a Raspberry Pi 5 for chamber deployment.

### Raspberry Pi OS Setup

**Requirements**

- Linux, MacOS, or Windows Subsystem for Linux
- [Ansible](https://docs.ansible.com/)
  - Linux/WSL: `apt install ansible`
  - MacOS: `brew install ansible`
- [NPEC Ansible Repository](git@github.com:txoof/ansible-npec.git) Cloned Locally
- 128 gigabyte high-performance micro SD Card (minimum)
- Micro SD Card adapter
- Raspberry Pi 5
- [Raspberry Pi Imager](https://www.raspberrypi.com/news/raspberry-pi-imager-imaging-utility/)
- Monitor & Keyboard
- Camera

#### WiFi Setup

1. Write Raspberry Pi OS Lite Trixie to the SD card
    - Username: `pi`
    - Password: the fleet `pi` password, from the team password manager
2. Connect the camera using the supplied ribbon cable, an extension cable and the AdaFruit DCI/CSI Thingie.
2. Insert the SD Card into the Pi, connect it to a monitor and boot
3. Login and run the following command to obtain the MAC address: `cat /sys/class/net/wlan0/address`. Note the MAC address value.

```shell
14:29:59
VER: Debian GNU/Linux 13 (trixie) (64 bit)
pi@testpi-02
[~]
$ cat /sys/class/net/wlan0/address
98:fe:54:50:f0:70
```

4. Create a login and password on the `iotroam` network for the device. Note the IP Address.
5. Configure the wifi adapter:

```shell
# Turn on wifi
$ sudo rfkill unblock wifi
$ nmcli radio wifi on
```

```shell
# set wifi region
$ sudo iw reg set NL
```

```
# Verify iotroam appears
$ nmcli device wifi rescan
$ nmcli device wifi list
$ nmcli device wifi list
IN-USE  BSSID              SSID                         
    08:55:31:C3:24:62  HADES-WIFI-2G                 
    08:55:31:C3:24:63  HADES-WIFI-5G                  
    F4:12:FA:E7:6F:09  CameraBack-E76F08             
    18:FD:74:BA:E6:9F  HELIOS-WIFI-2G                 
    F4:12:FA:E9:9C:91  CameraFront-E99C90             
    B0:1F:8C:94:74:22  iotroam                     
```

```shell
# Connect to the wifi - you will be prompted to enter the iotroam password
sudo nmcli --ask device wifi connect "iotroam"
```

```shell
# Verify the connetion
$ nmcli connection show --active
NAME        UUID                                  TYPE      DEVICE
iotroam     50186aba-763c-414c-9e3e-bbd70ab663dc  wifi      wlan0
tailscale0  40263dbd-380b-43ef-a1e8-74d3814cfe44  tun       tailscale0
lo          d500ade2-dc5a-4ff2-be3a-31ee9caa0e97  loopback  lo

$ ip addr show wlan0

# Note down the assigned IP address
3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 98:fe:54:50:f0:70 brd ff:ff:ff:ff:ff:ff
    inet 10.248.49.97/24 brd 10.248.49.255 scope global dynamic noprefixroute wlan0
       valid_lft 30375sec preferred_lft 30375sec
    inet6 fe80::61b8:3777:fb32:e2d/64 scope link noprefixroute
       valid_lft forever preferred_lft forever
```

#### Software Installation

Ansible will manage the initial onboarding of the Pi and software installation. The following commands should be run from inside the `ansible-npec` directory.

1. 



## Camera Mount Installation

![Camera Installation](./images/rig_assembly.png)
*Camera Rig Assembly*

### Materials

See the [Bill of Materials](./Bill-of-Materials.md) document for complete parts list and UU approved distributors.

| Qty | Item                                                                                                                | Notes |
| --- | ------------------------------------------------------------------------------------------------------------------- | ----- |
| 1   | 3 Gang Power Strip w 3m cable                                                                                       |       |
| 1   | 1.3m 40x40 t-chanel profile aluminum rail                                                                           |       |
| 1   | .4m 20x20 t-chanel profile aluminum rail                                                                            |       |
| 4   | M5x?? Bolts                                                                                                         |       |
| 4   | M6x?? Bolts                                                                                                         |       |
| 4   | M5 t-nut guided I-type slot 6 (20x20 compatible)                                                                    |       |
| 4   | M6 t-nut guided I-type slot 8 (40x40 compatible)                                                                    |       |
| 2   | 40x40 compatible 90 degree brackets                                                                                 |       |
| 2   | 20x20 compatible 90 degree brackets or [3D printed bracket](./exports/camera_rig/l_bracket_4020.stl)                           |       |
| 1   | [3D printed Cold Shoe Holder](./exports/camera_rig/m5_slide_pocket.stl)                                                        |       |
| 4   | [50mm Fiducial Tags](../reference/calibration-sheets/apriltags-36h11-50mm-a4-450-499.pdf) mounted on table brackets |       |
| 1   | Cold Shoe Adapter 3/8" to 1/4"                                                                                      |       |
| 1   | 1/4" compatible Ball Joint                                                                                          |       |
| 1   | ArduCam64 and appropriate cables                                                                                    |       |
| 1   | *Prepared Raspberry Pi 5 & Power Supply                                                                             |       |
|     | Zip Ties                                                                                                            |       |
| 1   | 1.5 m string                                                                                                        |       |
| 1   | Small heavy weight such as a nut                                                                                    |       |
|     | Scissors                                                                                                            |       |
|     | Hex Wrenches (5mm, 6mm)                                                                                             |       |
|     | Permanent marker (optional)                                                                                         |       |
|     | Double sided tape (optional)                                                                                        |       |

* See FIXME instructions for preparing the Raspberry Pi.

|                                               |                                                         |                                                        |                                                  |
| :-------------------------------------------: | :-----------------------------------------------------: | :----------------------------------------------------: | :----------------------------------------------: |
|        ![](images/arducam64_mount.png)        |             ![](images/l_bracket_4020.png)              |             ![](images/l_bracket_4040.png)             |         ![](images/m5_slide_pocket.png)          |
| [Camera Mount](./exports/camera_rig/arducam64_mount.stl) | [40x20 90 Degree Bracket](./exports/camera_rig/l_bracket_4020.stl) | [40x40 90 Degree Bracket](./images/l_bracket_4040.png) | [Cold Shoe Holder](./images/m5_slide_pocket.png) |

### Physical Installation Steps

Before starting: Ensure that the North and South TOP support 40x40 Profile rail are installed so the profile is exposed on the TOP of the rail. The default PSI install orients the channel facing down. It is possible to remove the corner braces, and rotate the bars in place without uninstalling them.

#### 40x40 Rail Installation

1. Loosely install the 90 degree bracket at either end of the 1.3m 40x40 t-chanel using the type 8 t-nuts and M6 bolts. Do not tighten. 
2. Install one type 8 t-nut on the left and right side of the rail.
3. Secure one 40x20 90 degree bracket to the left and right sides of the rail (see *Illustration 1* below)
4. Secure an M5 and type 6 t-nut to each of the 20mm brackets
5. Near the center of each profile, slot one type 8 t-nut into the top-support north and south 40x40 profile. *Note: this can be done in place; the nuts can be rotated such that they fit in to the chanel.*
6. Lay the 40x40 across the top support spanning the north and south supports
7. Loosely secure the 90 degree brackets to the north and south top support (see *Illustration 2* below). *Note: The rig will need to be centered. Avoid tightening the brackets until the end.*
8. Ensure the table is approximately in the center of the growth chamber
9. Slide the 40x40 rail so it roughly aligns with the seams in the light panels. The goal is to block as little light as possible.

|                                                                       |                                                         |
| :-------------------------------------------------------------------: | :-----------------------------------------------------: |
| ![40x20 90 degree Brackets](./images/rig_assembly_40x20-brackets.png) | ![40x40 Brackets](./images/rig_assembly_90-bracket.png) |
|                           *Illustration 1*                            |                    *Illustration 2*                     |
|                                                                       |                                                         |

#### 20x20 Bracket Installation

Do not attach the camera to the camera mount yet. This step establishes the coarse installation position.

1. Slot two type 6 t-nuts into the 20x20 profile rail
2. Loosely fasten the 3d printed cold-shoe holder to the 20x20 profile using 5mm bolts (see *Illustration 3*). *Note: The final position will need to be adjusted. Avoid tightening until the end*
3. Slot the cold-shoe adapter into the slot. Secure it using the included thumb screws
4. Install the ball-head on the cold-shoe adapter and firmly tighten the thumb screw against the base
5. Before attaching the ArduCam to the 3D printed camera mount, secure it to the ball head with the screw holes pointing down (see *Illustration 4*)
6. Slide the 20x20 rail onto the 20x40 brackets and losely secure it.

|                                                                           |                                                         |
| :-----------------------------------------------------------------------: | :-----------------------------------------------------: |
| ![3D printed Cold-Shoe Holder](./images/rig_assembly_m5_slide_pocket.png) | ![Ball Head Mount](./images/rig_assembly_ball-head.png) |
|                             *Illustration 3*                              |                    *Illustration 4*                     |
|    ![3D printed Camera Mount](./images/rig_assembly_camera-mount.png)     |   ![](./images/rig_assembly_assembled-20x20-rail.png)   |
|                             *Illustration 5*                              |                    *Illustration 6*                     |
|                                                                           |                                                         |

#### Fiducial Tag Installation

The 50mm fiducial tags need to be installed on the North and South edges of the table. They are located at the NW, SW, NE, SE corners. They are NOT located on the East and West edges of the table. Refer to the conventions illustration above. Attach the 50mm April Tags using XXX method The tags should be level with the floor and flush with the top edge of the table. It is not important which of the 50mm tags are used as long as all four are unique within this chamber.

Measure from the the outside of the table (not the leg) edge to the edge of the black border.

1. The NE and SE tags should be located 240mm from the East edge of the table.
2. The NW and SW tags should be located 425mm from the West edge of the table.

**NOTE:** The tags MUST be parallel along the North/South dimension. The precise location from the table edge are less important than ensuring that the East pair and west pair are at the same location. If they are offset to the east/west, calibration will be more complex and difficult.

#### Coarse Camera Centering

The camera needs to be located above the usable geographic center of the table. The drain area cannot be used for growth trays and must be excluded. The drain area is ~170mm wide. This method uses a weighted string to identify the center of the camera mount.

1. Move the North/South support so it rests under one of the seams in the light panels such that it blocks as little light as possible.
2. Lay a tape measure across the table from the East to the West across the "equator" of the table. Making marks on the East and West edges can help.
3. Identify the center of the table equator excluding unusable portion of the table around the drain. Making a mark on the tape measure at the center can help. 
4. Attach the string to the weight.
5. Attach the weighted string to the hole in the ArduCam mount so the weight is just over the surface of the table, but not touching the table
6. Orient the camera mount so it is roughly parallel with the surface of the table
7. Move the mount until the weight aligns with the mark on the tape measure. Make a mark on the table for reference.
8. Secure all the bolts around the table starting with the brackets and finishing with the camera mount.
9.  Make any fine adjustments so the weight is still aligned with the center of the table
10. Mark the outline of the brackets on the aluminum rail

#### Camera and Pi Installation

It is extremely difficult to work over the table. It is significantly easier to remove the 20x20 rail entirely for this portion. Only loosen the M5 bolts that secure the 20x20 to the 40x40 rail.

1. Slide the 20x20 rail off of the mounts.
2. Attach the Flat CSI/DSI to the ZIF socket on the camera per the supplier instructions. Make sure to orient the conductors appropriately. 
3. Thread the flat cable through the opening in the mount. If using the AdaFruit CSI/DSI Thingy, attach attach one end of the cable to the Pi5 Camera 0 slot.
4. Secure the camera using the mounting screws
5. Mount the camera to the ball-head
6. Attach the Pi to either the 40x40 bar or to the 20x20 bar using zip ties depending on cable length.
7. Remount the 20x20 bar using the marks to align the bar. Tighten the bolts.
8. Join the cables at the AdaFruit Thingy.
9. Plug in the Pi
10. Move on to the [Calibration and Setup section](#calibration-and-setup)

## Calibration and Setup

The camera should be 