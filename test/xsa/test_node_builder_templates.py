# test/xsa/test_node_builder_templates.py
from types import SimpleNamespace

from adidt.xsa.node_builder import NodeBuilder


def test_render_existing_template_returns_string():
    """_render loads an existing template and returns a non-empty string."""
    nb = NodeBuilder()
    # clkgen.tmpl needs instance.name, instance.base_addr, ps_clk_label, ps_clk_index
    ctx = {
        "instance": SimpleNamespace(name="test_clkgen", base_addr=0x43C00000),
        "ps_clk_label": "zynqmp_clk",
        "ps_clk_index": 71,
    }
    result = nb._render("clkgen.tmpl", ctx)
    assert isinstance(result, str)
    assert "test_clkgen" in result


def test_wrap_spi_bus_produces_overlay():
    nb = NodeBuilder()
    result = nb._wrap_spi_bus("spi0", "\t\tchild_node;\n")
    assert "\t&spi0 {" in result
    assert 'status = "okay";' in result
    assert "\t\tchild_node;" in result
    assert "\t};" in result


def test_hmc7044_template_renders_channel_with_freq_comment():
    ctx = {
        "label": "hmc7044",
        "cs": 0,
        "spi_max_hz": 1000000,
        "pll1_clkin_frequencies": [122880000, 0, 0, 0],
        "vcxo_hz": 122880000,
        "pll2_output_hz": 3_000_000_000,
        "clock_output_names_str": ", ".join(
            f'"hmc7044_out{i}"' for i in range(14)
        ),
        "jesd204_sysref_provider": True,
        "jesd204_max_sysref_hz": 2000000,
        "pll1_loop_bandwidth_hz": None,
        "pll1_ref_prio_ctrl": None,
        "pll1_ref_autorevert": False,
        "pll1_charge_pump_ua": None,
        "pfd1_max_freq_hz": None,
        "sysref_timer_divider": None,
        "pulse_generator_mode": None,
        "clkin0_buffer_mode": None,
        "clkin1_buffer_mode": None,
        "oscin_buffer_mode": None,
        "gpi_controls_str": "",
        "gpo_controls_str": "",
        "sync_pin_mode": None,
        "high_perf_mode_dist_enable": False,
        "channels": [
            {
                "id": 2,
                "name": "DEV_REFCLK",
                "divider": 12,
                "freq_str": "250 MHz",
                "driver_mode": 2,
                "coarse_digital_delay": None,
                "startup_mode_dynamic": False,
                "high_perf_mode_disable": False,
                "is_sysref": False,
            }
        ],
        "raw_channels": None,
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert "adi,divider = <12>; // 250 MHz" in out
    assert 'adi,extended-name = "DEV_REFCLK"' in out
    assert "hmc7044_c2: channel@2" in out
    assert "jesd204-sysref-provider;" in out


def test_hmc7044_template_sysref_channel_emits_sysref_flag():
    ctx = {
        "label": "hmc7044",
        "cs": 0,
        "spi_max_hz": 1000000,
        "pll1_clkin_frequencies": [122880000, 0, 0, 0],
        "vcxo_hz": 122880000,
        "pll2_output_hz": 3_000_000_000,
        "clock_output_names_str": ", ".join(
            f'"hmc7044_out{i}"' for i in range(14)
        ),
        "jesd204_sysref_provider": True,
        "jesd204_max_sysref_hz": 2000000,
        "pll1_loop_bandwidth_hz": 200,
        "pll1_ref_prio_ctrl": "0xE1",
        "pll1_ref_autorevert": True,
        "pll1_charge_pump_ua": 720,
        "pfd1_max_freq_hz": 1000000,
        "sysref_timer_divider": 1024,
        "pulse_generator_mode": 0,
        "clkin0_buffer_mode": "0x07",
        "clkin1_buffer_mode": "0x07",
        "oscin_buffer_mode": "0x15",
        "gpi_controls_str": "0x00 0x00 0x00 0x11",
        "gpo_controls_str": "0x1F 0x2B 0x00 0x00",
        "sync_pin_mode": None,
        "high_perf_mode_dist_enable": False,
        "channels": [
            {
                "id": 3,
                "name": "DEV_SYSREF",
                "divider": 3840,
                "freq_str": "781.25 kHz",
                "driver_mode": 2,
                "coarse_digital_delay": None,
                "startup_mode_dynamic": True,
                "high_perf_mode_disable": True,
                "is_sysref": True,
            }
        ],
        "raw_channels": None,
    }
    out = NodeBuilder()._render("hmc7044.tmpl", ctx)
    assert "adi,jesd204-sysref-chan;" in out
    assert "adi,startup-mode-dynamic-enable;" in out
    assert "adi,high-performance-mode-disable;" in out
    assert "adi,pll1-ref-prio-ctrl = <0xE1>;" in out
    assert "adi,pll1-ref-autorevert-enable;" in out


def test_ad9172_template_renders_device_node():
    ctx = {
        "label": "dac0_ad9172",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "hmc7044 2",
        "dac_rate_khz": 6000000,
        "jesd_link_mode": 9,
        "dac_interpolation": 1,
        "channel_interpolation": 1,
        "clock_output_divider": 1,
        "jesd_link_ids": [0],
        "jesd204_inputs": "axi_ad9172_core 0 0",
    }
    out = NodeBuilder()._render("ad9172.tmpl", ctx)
    assert 'compatible = "adi,ad9172"' in out
    assert "dac0_ad9172: ad9172@1" in out
    assert "adi,dac-rate-khz = <6000000>;" in out
    assert "jesd204-link-ids = <0>;" in out


def test_ad9523_1_template_renders_channel():
    ctx = {
        "label": "clk0_ad9523",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 125000000,
        "gpio_lines": [],
        "channels": [
            {"id": 4, "name": "ADC_CLK_FMC", "divider": 2, "freq_str": "500 MHz"},
        ],
    }
    out = NodeBuilder()._render("ad9523_1.tmpl", ctx)
    assert "clk0_ad9523" in out
    assert 'compatible = "adi,ad9523-1"' in out
    assert "adi,channel-divider = <2>; // 500 MHz" in out
    assert "adi,vcxo-freq" in out
    assert "ad9523_0_c4" in out  # label uses cs (0) in prefix


def test_ad9523_1_template_renders_sysref_channel():
    ctx = {
        "label": "clk0_ad9523",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 125000000,
        "gpio_lines": [],
        "channels": [
            {"id": 5, "name": "ADC_SYSREF", "divider": 128, "freq_str": "7.8125 MHz"},
        ],
    }
    out = NodeBuilder()._render("ad9523_1.tmpl", ctx)
    assert "ad9523_0_c5" in out
    # no signal_source property in this template
    assert "adi,signal-source" not in out


def _make_ad9680_ctx():
    # fmcdaq2-style: 3 clocks (jesd_label, device_clk, sysref_clk), no spi-cpol/cpha
    return {
        "label": "adc0_ad9680",
        "cs": 2,
        "spi_max_hz": 1000000,
        "use_spi_3wire": False,  # fmcdaq2: no spi-cpol/cpha/spi-3wire
        "clks_str": "<&axi_ad9680_jesd204_rx>, <&clk0_ad9523 13>, <&clk0_ad9523 5>",
        "clk_names_str": '"jesd_adc_clk", "adc_clk", "adc_sysref"',
        "sampling_frequency_hz": 1000000000,
        "m": 2, "l": 4, "f": 1, "k": 32, "np": 16,
        "jesd204_top_device": 0,
        "jesd204_link_ids": [0],
        "jesd204_inputs": "axi_ad9680_core 0 0",
        "gpio_lines": [],
    }


def test_ad9680_template_renders_device_node():
    out = NodeBuilder()._render("ad9680.tmpl", _make_ad9680_ctx())
    assert 'compatible = "adi,ad9680"' in out
    assert "adc0_ad9680: ad9680@2" in out
    assert "adi,octets-per-frame = <1>;" in out
    assert "jesd204-top-device = <0>;" in out
    assert 'clock-names = "jesd_adc_clk", "adc_clk", "adc_sysref";' in out
    assert "spi-cpol" not in out  # fmcdaq2 has no spi-cpol


def _make_ad9144_ctx():
    return {
        "label": "dac0_ad9144",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "clk0_ad9523 1",
        "jesd204_top_device": 1,
        "jesd204_link_ids": [0],
        # offset 1: AD9144 device node references the TPL core at link offset 1
        "jesd204_inputs": "axi_ad9144_core 1 0",
        "gpio_lines": [],
    }


def test_ad9144_template_renders_device_node():
    out = NodeBuilder()._render("ad9144.tmpl", _make_ad9144_ctx())
    assert 'compatible = "adi,ad9144"' in out
    assert "dac0_ad9144: ad9144@1" in out
    assert "jesd204-top-device = <1>;" in out
    assert "jesd204-inputs = <&axi_ad9144_core 1 0>;" in out
    assert "spi-cpol" not in out  # no spi-cpol in fmcdaq2 ad9144
    assert "adi,jesd-link-mode" not in out  # not present in fmcdaq2 ad9144


def test_adxcvr_template_2clk_variant():
    """fmcdaq2-style: 2 clocks, jesd L/M/S, no jesd204-inputs."""
    ctx = {
        "label": "axi_ad9680_adxcvr",
        "sys_clk_select": 0,
        "out_clk_select": 4,
        "clk_ref": "clk0_ad9523 4",
        "use_div40": True,
        "div40_clk_ref": "clk0_ad9523 4",
        "clock_output_names_str": '"adc_gt_clk", "rx_out_clk"',
        "use_lpm_enable": True,
        "jesd_l": 4,
        "jesd_m": 2,
        "jesd_s": 1,
        "jesd204_inputs": None,
        "is_rx": True,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert 'clock-names = "conv", "div40"' in out
    assert "adi,jesd-l = <4>;" in out
    assert "adi,use-lpm-enable;" in out
    assert "jesd204-inputs" not in out


def test_adxcvr_template_1clk_variant_with_jesd204_inputs():
    """fmcdaq3-style: 1 clock, jesd204-inputs present."""
    ctx = {
        "label": "axi_ad9680_xcvr",
        "sys_clk_select": 0,
        "out_clk_select": 8,
        "clk_ref": "clk0_ad9528 4",
        "use_div40": False,
        "div40_clk_ref": None,
        "clock_output_names_str": '"adc_gt_clk", "rx_out_clk"',
        "use_lpm_enable": True,
        "jesd_l": None,
        "jesd_m": None,
        "jesd_s": None,
        "jesd204_inputs": "clk0_ad9528 0 0",
        "is_rx": True,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert 'clock-names = "conv"' in out
    assert "jesd204-inputs = <&clk0_ad9528 0 0>;" in out
    assert "adi,jesd-l" not in out
    assert "adi,use-lpm-enable;" in out


def test_adxcvr_template_1clk_no_jesd204_inputs():
    """fmcdaq3 TX: 1 clock, no jesd204-inputs."""
    ctx = {
        "label": "axi_ad9152_xcvr",
        "sys_clk_select": 3,
        "out_clk_select": 8,
        "clk_ref": "clk0_ad9528 9",
        "use_div40": False,
        "div40_clk_ref": None,
        "clock_output_names_str": '"dac_gt_clk", "tx_out_clk"',
        "use_lpm_enable": True,
        "jesd_l": None,
        "jesd_m": None,
        "jesd_s": None,
        "jesd204_inputs": None,
        "is_rx": False,
    }
    out = NodeBuilder()._render("adxcvr.tmpl", ctx)
    assert "jesd204-inputs" not in out


def _make_jesd_overlay_ctx_rx():
    return {
        "label": "axi_ad9680_jesd204_rx",
        "direction": "rx",
        "clocks_str": "<&zynqmp_clk 71>, <&axi_ad9680_adxcvr 1>, <&axi_ad9680_adxcvr 0>",
        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
        "clock_output_name": "jesd_adc_lane_clk",
        "f": 1, "k": 32,
        "jesd204_inputs": "axi_ad9680_adxcvr 0 0",
        "converter_resolution": None,
        "converters_per_device": None,
        "bits_per_sample": None,
        "control_bits_per_sample": None,
    }


def test_jesd204_overlay_rx_does_not_emit_tx_fields():
    out = NodeBuilder()._render("jesd204_overlay.tmpl", _make_jesd_overlay_ctx_rx())
    assert "&axi_ad9680_jesd204_rx {" in out
    assert "#clock-cells = <0>;" in out
    assert "clock-output-names" in out
    assert "converter-resolution" not in out
    assert "adi,octets-per-frame = <1>;" in out


def test_jesd204_overlay_tx_emits_tx_fields():
    ctx = {
        "label": "axi_ad9144_jesd204_tx",
        "direction": "tx",
        "clocks_str": "<&zynqmp_clk 71>, <&axi_ad9144_adxcvr 1>, <&axi_ad9144_adxcvr 0>",
        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
        "clock_output_name": "jesd_dac_lane_clk",
        "f": 1, "k": 32,
        "jesd204_inputs": "axi_ad9144_adxcvr 1 0",
        "converter_resolution": 14,
        "converters_per_device": 2,
        "bits_per_sample": 16,
        "control_bits_per_sample": 2,
    }
    out = NodeBuilder()._render("jesd204_overlay.tmpl", ctx)
    assert "adi,converter-resolution = <14>;" in out
    assert "adi,converters-per-device = <2>;" in out
    assert "adi,control-bits-per-sample = <2>;" in out


def test_jesd204_overlay_ad9081_omits_clock_output_names():
    ctx = {
        "label": "axi_mxfe_rx_jesd_rx_axi",
        "direction": "rx",
        "clocks_str": "<&zynqmp_clk 71>, <&hmc7044 10>, <&axi_mxfe_rx_xcvr 0>",
        "clock_names_str": '"s_axi_aclk", "device_clk", "lane_clk"',
        "clock_output_name": None,
        "f": 4, "k": 32,
        "jesd204_inputs": "axi_mxfe_rx_xcvr 0 2",
        "converter_resolution": None,
        "converters_per_device": None,
        "bits_per_sample": None,
        "control_bits_per_sample": None,
    }
    out = NodeBuilder()._render("jesd204_overlay.tmpl", ctx)
    assert "#clock-cells = <0>;" in out
    assert "clock-output-names" not in out


def test_tpl_core_rx_template():
    ctx = {
        "label": "axi_ad9680_core",
        "compatible": "adi,axi-ad9680-1.0",
        "direction": "rx",
        "dma_label": "axi_ad9680_dma",
        "spibus_label": "adc0_ad9680",
        "jesd_label": "axi_ad9680_jesd204_rx",
        "jesd_link_offset": 0,
        "link_id": 0,
        "pl_fifo_enable": False,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert "&axi_ad9680_core {" in out
    assert 'dma-names = "rx";' in out
    assert "spibus-connected = <&adc0_ad9680>;" in out
    assert "adi,axi-pl-fifo-enable" not in out
    assert "jesd204-inputs = <&axi_ad9680_jesd204_rx 0 0>;" in out


def test_tpl_core_tx_has_fifo_enable():
    ctx = {
        "label": "axi_ad9144_core",
        "compatible": "adi,axi-ad9144-1.0",
        "direction": "tx",
        "dma_label": "axi_ad9144_dma",
        "spibus_label": "dac0_ad9144",
        "jesd_label": "axi_ad9144_jesd204_tx",
        "jesd_link_offset": 1,
        "link_id": 0,
        "pl_fifo_enable": True,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert 'dma-names = "tx";' in out
    assert "adi,axi-pl-fifo-enable;" in out
    assert "jesd204-inputs = <&axi_ad9144_jesd204_tx 1 0>;" in out


def test_tpl_core_ad9172_no_dma():
    ctx = {
        "label": "axi_ad9172_core",
        "compatible": "adi,axi-ad9172-1.0",
        "direction": "tx",
        "dma_label": None,
        "spibus_label": "dac0_ad9172",
        "jesd_label": "axi_ad9172_jesd_tx_axi",
        "jesd_link_offset": 0,
        "link_id": 0,
        "pl_fifo_enable": True,
        "sampl_clk_ref": None,
        "sampl_clk_name": None,
    }
    out = NodeBuilder()._render("tpl_core.tmpl", ctx)
    assert "dmas" not in out
    assert "dma-names" not in out


def test_ad9528_template_renders_pll_channel():
    ctx = {
        "label": "clk0_ad9528",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 100000000,
        "gpio_lines": [],
        "channels": [
            {
                "id": 1,
                "name": "ADC_CLK",
                "divider": 3,
                "freq_str": "411.11 MHz",
                "signal_source": 0,
                "is_sysref": False,
            }
        ],
    }
    out = NodeBuilder()._render("ad9528.tmpl", ctx)
    assert 'compatible = "adi,ad9528"' in out
    assert "clk0_ad9528" in out
    assert "adi,channel-divider = <3>;" in out
    assert "// 411.11 MHz" in out
    assert "adi,vcxo-freq" in out
    assert "ad9528_0_c1" in out
    assert "adi,pll2-m1-frequency" in out


def test_ad9152_template_renders_device_node():
    ctx = {
        "label": "dac0_ad9152",
        "cs": 1,
        "spi_max_hz": 1000000,
        "clk_ref": "clk0_ad9528 9",
        "jesd_link_mode": 9,
        "jesd204_top_device": 1,
        "jesd204_link_ids": [0],
        "jesd204_inputs": "axi_ad9152_core 1 0",
        "gpio_lines": [],
    }
    out = NodeBuilder()._render("ad9152.tmpl", ctx)
    assert 'compatible = "adi,ad9152"' in out
    assert "dac0_ad9152: ad9152@1" in out
    assert "spi-cpol;" in out
    assert "adi,spi-3wire-enable;" in out
    assert "adi,jesd-link-mode = <9>;" in out
    assert "jesd204-top-device = <1>;" in out
    assert "jesd204-inputs = <&axi_ad9152_core 1 0>;" in out


def test_ad9081_mxfe_template_renders_device_node():
    ctx = {
        "label": "trx0_ad9081",
        "cs": 0,
        "spi_max_hz": 5000000,
        "gpio_label": "gpio",
        "reset_gpio": 133,
        "sysref_req_gpio": 121,
        "rx2_enable_gpio": 135,
        "rx1_enable_gpio": 134,
        "tx2_enable_gpio": 137,
        "tx1_enable_gpio": 136,
        "dev_clk_ref": "hmc7044 2",
        "rx_core_label": "rx_mxfe_tpl_core_adc_tpl_core",
        "tx_core_label": "tx_mxfe_tpl_core_dac_tpl_core",
        "rx_link_id": 2,
        "tx_link_id": 0,
        "dac_frequency_hz": 12_000_000_000,
        "tx_cduc_interpolation": 8,
        "tx_fduc_interpolation": 6,
        "tx_converter_select": "<0x00> <0xFF>",
        "tx_lane_map": "0 1 2 3 4 5 6 7",
        "tx_link_mode": 9,
        "tx_m": 8, "tx_f": 4, "tx_k": 32, "tx_l": 4, "tx_s": 1,
        "adc_frequency_hz": 4_000_000_000,
        "rx_cddc_decimation": 4,
        "rx_fddc_decimation": 4,
        "rx_converter_select": "<0x00> <0xFF>",
        "rx_lane_map": "0 1 2 3 4 5 6 7",
        "rx_link_mode": 9,
        "rx_m": 8, "rx_f": 4, "rx_k": 32, "rx_l": 4, "rx_s": 1,
    }
    out = NodeBuilder()._render("ad9081_mxfe.tmpl", ctx)
    assert 'compatible = "adi,ad9081"' in out
    assert "trx0_ad9081: ad9081@0" in out
    assert "adi,tx-dacs" in out
    assert "adi,rx-adcs" in out
    assert "adi,dac-frequency-hz = /bits/ 64 <12000000000>;" in out
    assert "adi,adc-frequency-hz = /bits/ 64 <4000000000>;" in out
    assert "jesd204-link-ids = <2 0>;" in out


def test_ad9528_1_template_renders_channel():
    ctx = {
        "label": "clk0_ad9528",
        "cs": 0,
        "spi_max_hz": 10000000,
        "vcxo_hz": 122880000,
        "gpio_lines": [],
        "channels": [
            {
                "id": 13,
                "name": "DEV_CLK",
                "divider": 5,
                "freq_str": "245.76 MHz",
                "signal_source": 0,
                "is_sysref": False,
            }
        ],
    }
    out = NodeBuilder()._render("ad9528_1.tmpl", ctx)
    assert 'compatible = "adi,ad9528"' in out
    assert "clk0_ad9528: ad9528-1@0" in out
    assert "adi,channel-divider = <5>;" in out
    assert "// 245.76 MHz" in out
    assert "adi,vcxo-freq = <122880000>;" in out
    assert "ad9528_0_c13" in out
    assert "adi,refa-enable" in out
    assert "adi,pll2-n2-div" in out
    assert '"ad9528-1_out0"' in out
