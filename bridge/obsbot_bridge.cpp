#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>

#include <dev/devs.hpp>
#include <dev/dev.hpp>

namespace py = pybind11;

PYBIND11_MODULE(obsbot_bridge, m)
{
	m.doc() = "Thin pybind11 bridge over the OBSBOT libdev SDK";

	py::enum_<ObsbotProductType>(m, "ProductType")
		.value("Tiny", ObsbotProdTiny)
		.value("Tiny4k", ObsbotProdTiny4k)
		.value("Tiny2", ObsbotProdTiny2)
		.value("Tiny2Lite", ObsbotProdTiny2Lite)
		.value("TinySE", ObsbotProdTinySE)
		.export_values();

	m.def("list_devices", []() {
		py::list out;
		for (auto &dev : Devices::get().getDevList()) {
			py::dict item;
			item["sn"] = dev->devSn();
			item["name"] = dev->devName();
			item["product_type"] = dev->productType();
			out.append(item);
		}
		return out;
	});
}
