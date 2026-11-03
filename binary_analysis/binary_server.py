
import pefile
from pathlib import Path
from capstone import *
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Binary Analysis Server")


@mcp.tool()
def analyze_binary(binary_path: str) -> str:
    """Analyze a Windows executable and list its basic information."""

    file_path = Path(binary_path)

    if not file_path.exists():
        return f"Binary file not found: {binary_path}"

    try:
        pe = pefile.PE(str(file_path))

        results = []

        results.append(f"File: {file_path.name}")
        results.append(f"Architecture: {hex(pe.FILE_HEADER.Machine)}")
        results.append(
            f"Number of sections: {pe.FILE_HEADER.NumberOfSections}"
        )
        results.append(
            f"Entry point: {hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)}"
        )

        results.append("\nSections:")

        for section in pe.sections:
            section_name = section.Name.decode(
                errors="ignore"
            ).rstrip("\x00")

            results.append(
                f"Section: {section_name} | "
                f"Size: {section.SizeOfRawData}"
            )

        return "\n".join(results)

    except pefile.PEFormatError:
        return "Invalid or unsupported Windows PE binary."

    except Exception as error:
        return f"Binary analysis failed: {error}"


@mcp.tool()
def find_binary_functions(binary_path: str) -> str:
    """Find exported functions in a Windows executable or DLL."""

    file_path = Path(binary_path)

    if not file_path.exists():
        return f"Binary file not found: {binary_path}"

    try:
        pe = pefile.PE(str(file_path))

        if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            return "No exported functions found in this binary."

        results = []

        for function in pe.DIRECTORY_ENTRY_EXPORT.symbols:

            if function.name:
                name = function.name.decode(
                    errors="ignore"
                )
            else:
                name = f"Ordinal_{function.ordinal}"

            address = hex(function.address)

            results.append(
                f"Function: {name} | Address: {address}"
            )

        if not results:
            return "No exported functions found."

        return "\n".join(results)

    except pefile.PEFormatError:
        return "Invalid or unsupported Windows PE binary."

    except Exception as error:
        return f"Function discovery failed: {error}"

@mcp.tool()
def disassemble_binary(binary_path: str, max_instructions: int = 50) -> str:
    """Disassemble instructions from a Windows executable."""

    file_path = Path(binary_path)

    if not file_path.exists():
        return f"Binary file not found: {binary_path}"

    try:
        pe = pefile.PE(str(file_path))

        machine = pe.FILE_HEADER.Machine

        # Select architecture
        if machine == 0x14c:
            md = Cs(CS_ARCH_X86, CS_MODE_32)

        elif machine == 0x8664:
            md = Cs(CS_ARCH_X86, CS_MODE_64)

        else:
            return "Unsupported binary architecture."

        entry_point = pe.OPTIONAL_HEADER.AddressOfEntryPoint

        image_base = pe.OPTIONAL_HEADER.ImageBase

        # Convert entry point to file offset
        file_offset = pe.get_offset_from_rva(entry_point)

        # Read machine code from the entry point
        code = pe.__data__[file_offset:file_offset + 500]

        instructions = []

        address = image_base + entry_point

        for instruction in md.disasm(code, address):

            instructions.append(
                f"{hex(instruction.address)}: "
                f"{instruction.mnemonic} "
                f"{instruction.op_str}"
            )

            if len(instructions) >= max_instructions:
                break

        if not instructions:
            return "No instructions could be disassembled."

        return "\n".join(instructions)

    except pefile.PEFormatError:
        return "Invalid or unsupported Windows PE binary."

    except Exception as error:
        return f"Disassembly failed: {error}"

if __name__ == "__main__":
    mcp.run()
