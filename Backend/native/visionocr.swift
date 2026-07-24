// visionocr — native macOS OCR helper for the DocDigitizer backend.
//
// Uses Apple's Vision framework (on-device, offline, Neural-Engine accelerated)
// to recognize text. The Python pipeline calls this per page and gets JSON with
// per-line text, confidence and normalized bounding boxes. This replaces
// Tesseract for the faithful-overlay text layer and the confidence probe, and
// feeds the light (native) reconstruction route.
//
// Build:   swiftc -O visionocr.swift -o ../bin/visionocr
// Usage:   visionocr --langs de-DE,en-US page1.png page2.png …
//          visionocr --list-langs
//
// Output (stdout, UTF-8 JSON):
//   {"pages":[{"path":…,"width":px,"height":px,"mean_confidence":0..1,
//              "lines":[{"text":…,"confidence":0..1,
//                        "x":0..1,"y":0..1,"w":0..1,"h":0..1}]}]}
// Bounding boxes are normalized with a BOTTOM-LEFT origin (Vision convention);
// the Python side converts to top-left points.

import Foundation
import Vision
import ImageIO
import CoreGraphics

struct LineOut: Codable {
    let text: String
    let confidence: Double
    let x: Double, y: Double, w: Double, h: Double
}

struct PageOut: Codable {
    let path: String
    let width: Int
    let height: Int
    let mean_confidence: Double
    let lines: [LineOut]
}

struct OCROutput: Codable {
    let pages: [PageOut]
}

func loadCGImage(_ path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else { return nil }
    return cg
}

func recognize(_ path: String, langs: [String]) -> PageOut {
    guard let cg = loadCGImage(path) else {
        FileHandle.standardError.write(Data("visionocr: cannot load \(path)\n".utf8))
        return PageOut(path: path, width: 0, height: 0, mean_confidence: 0, lines: [])
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    if !langs.isEmpty { request.recognitionLanguages = langs }

    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write(Data("visionocr: perform failed for \(path): \(error)\n".utf8))
    }

    let observations = request.results ?? []
    var lines: [LineOut] = []
    var confSum = 0.0
    for obs in observations {
        guard let cand = obs.topCandidates(1).first else { continue }
        let bb = obs.boundingBox  // normalized, bottom-left origin
        lines.append(LineOut(
            text: cand.string,
            confidence: Double(cand.confidence),
            x: Double(bb.origin.x), y: Double(bb.origin.y),
            w: Double(bb.size.width), h: Double(bb.size.height)))
        confSum += Double(cand.confidence)
    }
    let mean = lines.isEmpty ? 0.0 : confSum / Double(lines.count)
    return PageOut(path: path, width: cg.width, height: cg.height,
                   mean_confidence: mean, lines: lines)
}

// ---- argument parsing ----
var langs = ["de-DE", "en-US"]
var paths: [String] = []
var args = CommandLine.arguments.dropFirst().makeIterator()
while let arg = args.next() {
    switch arg {
    case "--langs":
        if let v = args.next() { langs = v.split(separator: ",").map(String.init) }
    case "--list-langs":
        let req = VNRecognizeTextRequest()
        let supported = (try? req.supportedRecognitionLanguages()) ?? []
        print(supported.joined(separator: "\n"))
        exit(0)
    default:
        paths.append(arg)
    }
}

let output = OCROutput(pages: paths.map { recognize($0, langs: langs) })
let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]
let data = (try? encoder.encode(output)) ?? Data("{\"pages\":[]}".utf8)
FileHandle.standardOutput.write(data)
