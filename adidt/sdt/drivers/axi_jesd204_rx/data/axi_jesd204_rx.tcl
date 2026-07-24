# SPDX-License-Identifier: GPL-2.0-or-later
#
# ADI AXI JESD204 RX SDT driver proof of concept.
# The definition proc is deliberately side-effect free so stock tclsh can
# validate this file without loading HSI or SDTGen.

namespace eval ::adidt::sdt::axi_jesd204_rx {
    variable definition [dict create \
        schema_version 1 \
        name axi_jesd204_rx \
        supported_ip_names {axi_jesd204_rx} \
        supported_vlnv_globs {analog.com:user:axi_jesd204_rx:*} \
        generator_proc axi_jesd204_rx_generate \
        output_files {pl.dtsi} \
        architectures {zynq zynqmp versal microblaze} \
        required_hsi_properties {CONFIG.C_NUM_LANES CONFIG.C_DATA_PATH_WIDTH} \
        required_interfaces {s_axi s_axi_aclk core_clk irq} \
        compatibles {adi,axi-jesd204-rx-1.0 adi,axi-jesd204-rx-1.3} \
        binding Documentation/devicetree/bindings/iio/jesd204/adi,jesd204-rx.txt \
        binding_format legacy-text \
        emitted_properties [dict create compatible stringlist]]

    proc definition {} {
        variable definition
        return $definition
    }

    proc generate {drv_handle} {
        set ip_name [::hsi get_property IP_NAME $drv_handle]
        if {$ip_name ne "axi_jesd204_rx"} {
            error "axi_jesd204_rx driver received unsupported IP '$ip_name'"
        }
        set node_command [namespace which -command ::sdtgen::get_node]
        if {$node_command eq ""} {
            set node_command [namespace which -command ::get_node]
        }
        if {$node_command eq ""} {
            error "get_node helper unavailable; commands: [info commands ::*get_node*] [info commands ::*::*get_node*]"
        }
        set node [$node_command $drv_handle]
        if {$node == 0} {
            error "no SDT node exists for $drv_handle"
        }
        # Common SDT generation has already created reg, interrupt and clock
        # properties from HSI. Replace only the generic Xilinx compatible.
        set tree_command [namespace which -command ::sdtgen::pldt]
        if {$tree_command eq ""} {
            set tree_command [namespace which -command ::pldt]
        }
        if {$tree_command eq ""} {
            error "pldt helper unavailable"
        }
        $tree_command set $node compatible {"adi,axi-jesd204-rx-1.0"}
    }
}

proc axi_jesd204_rx_generate {drv_handle} {
    ::adidt::sdt::axi_jesd204_rx::generate $drv_handle
}
