// Synthetic resource only: no game installation, anti-cheat or commercial assets.
#include <d3d11.h>
#include <d3dcompiler.h>
#include <cstdio>

template <typename T> struct Ref {
  T *value = nullptr;
  ~Ref() { if (value) value->Release(); }
  T **out() { return &value; }
  T *operator->() { return value; }
};

static bool check(HRESULT hr, const char *step) {
  if (SUCCEEDED(hr)) return true;
  std::printf("FAIL %s HRESULT=%08lx\n", step, (unsigned long)hr);
  return false;
}

int main() {
  Ref<ID3D11Device> device;
  Ref<ID3D11DeviceContext> context;
  D3D_FEATURE_LEVEL level;
  if (!check(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0,
                              D3D11_SDK_VERSION, device.out(), &level, context.out()), "CreateDevice")) return 1;
  char module[MAX_PATH]{};
  GetModuleFileNameA(GetModuleHandleA("d3d11.dll"), module, MAX_PATH);
  std::printf("D3D11 module=%s feature_level=%04x\n", module, (unsigned)level);
  const char source[] = "RWBuffer<uint> output : register(u0);"
                       "[numthreads(1,1,1)] void main(uint3 id:SV_DispatchThreadID){output[0]=42;}";
  Ref<ID3DBlob> bytecode, errors;
  HRESULT hr = D3DCompile(source, sizeof(source), "dxmt_synthetic", nullptr, nullptr, "main", "cs_5_0", 0, 0,
                         bytecode.out(), errors.out());
  if (!check(hr, "D3DCompile")) {
    if (errors.value) std::printf("%s\n", (char *)errors->GetBufferPointer());
    return 2;
  }
  Ref<ID3D11ComputeShader> shader;
  if (!check(device->CreateComputeShader(bytecode->GetBufferPointer(), bytecode->GetBufferSize(), nullptr, shader.out()), "CreateComputeShader")) return 3;
  D3D11_BUFFER_DESC desc{};
  desc.ByteWidth = sizeof(UINT);
  desc.Usage = D3D11_USAGE_DEFAULT;
  desc.BindFlags = D3D11_BIND_UNORDERED_ACCESS;
  Ref<ID3D11Buffer> output, staging;
  if (!check(device->CreateBuffer(&desc, nullptr, output.out()), "CreateBuffer")) return 4;
  D3D11_UNORDERED_ACCESS_VIEW_DESC view{};
  view.Format = DXGI_FORMAT_R32_UINT;
  view.ViewDimension = D3D11_UAV_DIMENSION_BUFFER;
  view.Buffer.NumElements = 1;
  Ref<ID3D11UnorderedAccessView> uav;
  if (!check(device->CreateUnorderedAccessView(output.value, &view, uav.out()), "CreateUAV")) return 5;
  context->CSSetShader(shader.value, nullptr, 0);
  context->CSSetUnorderedAccessViews(0, 1, &uav.value, nullptr);
  context->Dispatch(1, 1, 1);
  desc.Usage = D3D11_USAGE_STAGING;
  desc.BindFlags = desc.MiscFlags = desc.StructureByteStride = 0;
  desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
  if (!check(device->CreateBuffer(&desc, nullptr, staging.out()), "CreateReadback")) return 6;
  context->CopyResource(staging.value, output.value);
  D3D11_MAPPED_SUBRESOURCE mapped{};
  if (!check(context->Map(staging.value, 0, D3D11_MAP_READ, 0, &mapped), "Readback")) return 7;
  UINT result = *(UINT *)mapped.pData;
  context->Unmap(staging.value, 0);
  context->ClearState();
  context->Flush();
  std::printf("COMPUTE_RESULT=%u\n", result);
  return result == 42 ? 0 : 8;
}
