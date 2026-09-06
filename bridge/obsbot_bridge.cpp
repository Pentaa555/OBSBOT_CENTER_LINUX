#include <pybind11/pybind11.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <iostream>
#include <stdexcept>
#include <string>

#include <dev/devs.hpp>
#include <dev/dev.hpp>

namespace py = pybind11;

struct ObsbotError : public std::runtime_error {
	using std::runtime_error::runtime_error;
};

static void check_ok(int32_t ret, const char *what)
{
	if (ret != RM_RET_OK) {
		throw ObsbotError(std::string(what) + " failed with code " +
				   std::to_string(ret));
	}
}

static py::dict status_to_dict(const Device::CameraStatus &status)
{
	py::dict d;
	d["zoom_ratio"] = status.tiny.zoom_ratio;
	d["ai_mode"] = status.tiny.ai_mode;
	d["dev_status"] = status.tiny.dev_status;
	d["vertical"] = status.tiny.vertical;
	d["hdr"] = status.tiny.hdr;
	return d;
}

PYBIND11_MODULE(obsbot_bridge, m)
{
	m.doc() = "Thin pybind11 bridge over the OBSBOT libdev SDK";

	py::register_exception<ObsbotError>(m, "ObsbotError");

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
		.def_property_readonly("product_type", &Device::productType)
		.def("set_status_callback", [](Device &d, py::function callback) {
			auto shared_cb = std::make_shared<py::function>(std::move(callback));
			d.setDevStatusCallbackFunc(
				[shared_cb](void *, const void *data) {
					const auto *status =
						static_cast<const Device::CameraStatus *>(data);
					py::gil_scoped_acquire acquire;
					try {
						(*shared_cb)(status_to_dict(*status));
					} catch (const std::exception &e) {
						std::cerr << "status callback error: "
							  << e.what() << std::endl;
					}
				},
				nullptr);
			d.enableDevStatusCallback(true);
		});

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
