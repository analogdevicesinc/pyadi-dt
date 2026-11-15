"""DMA cores built cache-coherent must be declared so in the device tree."""

from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import AxiIpInstance, XsaTopology


def _dma(name: str, coherent: str | None) -> AxiIpInstance:
    parameters = {} if coherent is None else {"CACHE_COHERENT": coherent}
    return AxiIpInstance(
        name=name,
        ip_type="axi_dmac",
        base_addr=0x9C420000,
        size=0x1000,
        irq=109,
        parameters=parameters,
    )


def test_only_coherent_dma_cores_are_marked():
    topology = XsaTopology(
        ip_instances=[
            _dma("axi_rx_dma", "true"),
            _dma("axi_tx_dma", "false"),
            _dma("axi_old_dma", None),
        ]
    )
    overlays = NodeBuilder._coherent_dma_overlays(topology)
    assert overlays == ["\t&axi_rx_dma {\n\t\tdma-coherent;\n\t};"]
