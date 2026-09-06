#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <iostream>

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

	py::class_<Device, std::shared_ptr<Device>>(m, "Device")
		.def_property_readonly("sn", &Device::devSn)
		.def_property_readonly("name", [](Device &d) { return d.devName(); })
		.def_property_readonly("product_type", &Device::productType);

	m.def("get_device_by_sn", [](const std::string &sn) {
		return Devices::get().getDevBySn(sn);
	});

	m.def("set_device_changed_callback", [](py::function callback) {
		static py::function stored_callback;
		stored_callback = std::move(callback);
		Devices::get().setDevChangedCallback(
			[](std::string sn, bool connected, void *) {
				py::gil_scoped_acquire acquire;
				try {
					stored_callback(sn, connected);
				} catch (const std::exception &e) {
					std::cerr << "device changed callback error: "
						  << e.what() << std::endl;
				}
			},
			nullptr);
	});

	m.def("close", []() { Devices::get().close(); });

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
