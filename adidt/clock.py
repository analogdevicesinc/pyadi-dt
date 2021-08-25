
import adidt.dt as dt
import adidt.parts as parts

class clock(dt):
    supported_parts = ['HMC7044','AD9523-1']

    def _to_class_naming(self,name):
        return name.lower().replace('-',"_")

    def set(self, part:str, config):

        if part not in self.supported_parts:
            raise Exception(f"Unknown or unsupported part: {part}")

        dev = eval(f"parts.{self._to_class_naming(part)}_dt()")

        # Check if node in dt
        node = self.get_node_by_compatible(dev.compatible_id)
        if not node:
            raise Exception(f"No DT node found for {part} ({dev.compatible_id})")
        if len(node)>1:
            raise Exception(f"Too many nodes found with name {dev.compatible_id}. Must supply node name")

        dev.set_dt_node_from_config(node[0],config)

        

        
